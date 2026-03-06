#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HiddenTube Preview Flow GUI v3

주요 기능
- tkinter 기반 로컬 GUI
- 노드 체인 순차 실행
- 별도 프롬프트 템플릿 편집창
- 이전 모든 노드 참조 가능
- 참조 토큰 문법 확장:
  - {{node_key}}
  - {{node_key.field}}
  - {{node_key.field.subfield}}
  - {{node_key.list_field[0]}}
  - {{node_key.list_field[0].field}}
- 칩(Chip) UI 기반 참조 패널
- 클릭 삽입 + 드래그 앤 드롭 삽입
- 노드 전체 / 하위 필드 / 중첩 필드 자동 탐색
- 렌더링 시 문자열은 그대로, dict/list는 pretty JSON 치환
- 없는 노드/필드/인덱스/미완료 노드 참조 시 저장/실행 차단
- 외부 LLM 응답은 JSON 아니어도 무조건 저장 허용
"""

from __future__ import annotations

import argparse
import json
import re
import textwrap
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


SESSION_FILE = "preview_flow_session.json"
OUTPUT_FILE = "output_ffmpeg_plan.json"


DEFAULT_PROMPTS: Dict[str, str] = {
    "script_generation": textwrap.dedent(
        """
        **[역할 설정]**
        너는 구독자 100만 명을 보유한 시니어 전문 건강 유튜버다.
        말투는 따뜻하고 친절하지만, 의학적 전문성이 느껴지는 권위 있는 전문가
        (예: 독일 의사, 70대 영양학 박사) 페르소나를 가져야 한다.

        **[미션]**
        제공된 건강 정보를 바탕으로
        시니어 시청자(60~80대)와 자녀 세대가 이해하기 쉬운
        유튜브 쇼츠용 건강 콘텐츠를 작성한다.

        **[출력 목표]**
        - 쇼츠 길이: TTS 기준 약 52~58초
        - 이후 단계(scene_breakdown, image_prompt, ffmpeg_json)에서
        바로 사용할 수 있도록 **JSON 구조로 출력**

        ------------------------------------------------------------

        **[대본 구성 원칙: 7단계 구조]**

        대본은 반드시 아래 흐름을 따른다.

        1. 강력한 도입부 (Hook & Authority)
        2. 공감 사례 (Empathy)
        3. 쉬운 비유 설명 (Simple Analogy)
        4. 정보의 수치화 (Numbered List)
        5. 실천 가능한 해결책 (Actionable Step)
        6. 전문가 경고 및 안전 수칙 (Safety First)
        7. 따뜻한 마무리 + CTA (Closing)

        ※ 반드시 이 흐름을 유지할 것

        ------------------------------------------------------------

        **[작성 스타일 가이드]**

        어투
        - "~하시죠?"
        - "~입니다"
        - "어르신들"
        - "어머님들"

        톤
        - 따뜻하고 신뢰감 있는 전문가
        - 과도한 공포 연출 금지

        비유
        - 시각적인 생활 비유 사용

        건강 정보 규칙
        - 질병 진단 단정 금지
        - 치료 단정 금지
        - 반드시 "가능성", "도움이 될 수 있습니다" 등 완화 표현 사용

        ------------------------------------------------------------

        **[숫자 표현 규칙]**

        TTS 읽기 기준

        숫자는 가능한 말로 표현

        예
        3분 → "세 분"
        5도 → "오 도"
        2시간 → "두 시간"

        ------------------------------------------------------------

        **[입력 데이터]**

        {{content_input}}

        ------------------------------------------------------------

        **[출력 요청]**

        아래 JSON 구조로만 출력

        - 설명 금지
        - 일반 텍스트 금지
        - JSON 코드블록만 출력
        - JSON 문법 오류 절대 금지

        ------------------------------------------------------------

        **[JSON 전체 메타 키]**

        반드시 아래 키 포함

        - title
        - topic
        - target_audience
        - tone
        - safety_notes
        - cta
        - estimated_total_duration_sec
        - script
        - subtitle_lines
        - keywords
        - structure

        ------------------------------------------------------------

        **[값 생성 규칙]**

        title  
        - 영상 제목
        - 시니어 채널에 맞는 이해하기 쉬운 제목

        topic  
        - 건강 주제 한 줄 요약

        target_audience  
        - 기본값: "60~80대 시니어 및 자녀 세대"

        tone  
        - "따뜻하고 신뢰감 있는 건강 정보"

        safety_notes  
        - 건강 콘텐츠 안전 문구
        예
        "본 콘텐츠는 건강 정보를 이해하기 쉽게 설명하기 위한 일반 정보이며, 증상이나 질환이 의심될 경우 반드시 전문의 상담이 필요합니다."

        cta  
        - 자연스러운 구독 유도 문장

        estimated_total_duration_sec  
        - 52~58 사이 숫자

        script  
        - TTS용 전체 내레이션 원문
        - 문단 구분 가능

        subtitle_lines  
        - 자막용 문장 배열
        - 한 줄 10~20자 정도
        - 총 10~18줄 권장
        - 의미 단위로 끊기

        keywords  
        - 핵심 키워드 5~10개
        - 배열 형태

        structure  
        - 대본 구조 설명 배열
        - 아래 7단계 반드시 포함

        structure 값 예

        [
        "Hook",
        "Empathy",
        "Analogy",
        "Numbers",
        "Solution",
        "Safety",
        "Closing"
        ]

        ------------------------------------------------------------

        **[중요 규칙]**

        절대 하지 말 것

        - JSON 외 텍스트 출력
        - 장면 분해 작성
        - 이미지 프롬프트 생성
        - FFmpeg 구조 생성

        이번 단계는 **대본 생성만 수행**

        ------------------------------------------------------------

        **[최종 출력 예시 형식]**

        ```json
        {
        "title": "...",
        "topic": "...",
        "target_audience": "...",
        "tone": "...",
        "safety_notes": "...",
        "cta": "...",
        "estimated_total_duration_sec": 55,
        "script": "...",
        "subtitle_lines": [
            "...",
            "...",
            "..."
        ],
        "keywords": [
            "...",
            "...",
            "..."
        ],
        "structure": [
            "Hook",
            "Empathy",
            "Analogy",
            "Numbers",
            "Solution",
            "Safety",
            "Closing"
        ]
        }
        """
    ).strip(),
    "scene_breakdown": textwrap.dedent(
        """
        {{script_generation}}을 기준으로 **장면 분해표(Scene Breakdown)용 JSON만** 만들어줘.
        (대본 자체를 다시 쓰지 말고, 기존 대본을 장면 설계용으로만 구조화)

        [출력 요청]
        - 반드시 **JSON 코드블록으로만 출력**
        - 설명 / 주석 / 머리말 / 마무리 문장 / 표 / 일반 텍스트 출력 금지
        - 장면 분해만 수행하고, 새로운 대본/메시지/정보를 창작하지 말 것
        - script_generation에 있는 내용을 기준으로만 장면화할 것
        - JSON 문법 오류 절대 금지
        - 숫자 필드는 반드시 number 타입
        - 장면 배열 순서 유지

        ------------------------------------------------------------
        [장면 분해 목표]
        쇼츠 대본을 바탕으로 장면별 설계만 수행한다.

        각 장면에는 아래 정보를 구조화:
        - 장면 번호
        - 장면 목적
        - 해당 대사 요약
        - 화면 핵심 요소
        - 권장 장면 길이(초)
        - B-roll 성격
        - 대체 컷 아이디어 2개

        ------------------------------------------------------------
        [장면 수 규칙]
        - 장면 수는 과도하게 늘리지 말 것
        - 기본적으로 6~10컷 내외
        - 단, script_generation의 실제 길이와 내용 흐름상 더 적거나 많아야 자연스러우면 최소한으로 조정 가능
        - 불필요하게 세분화하지 말 것
        - 같은 의미가 이어지는 문장은 가능한 한 하나의 장면으로 묶을 것

        ------------------------------------------------------------
        [시니어 채널 톤 규칙]
        - 과도한 공포 이미지 금지
        - 혐오감/고어/충격 연출 금지
        - 따뜻하고 신뢰감 있는 건강/정보 채널 톤 유지
        - 경고 장면도 위협보다는 “주의 + 안심 가능한 해결 방향” 중심

        ------------------------------------------------------------
        [장면 목적 분류 규칙]
        scene purpose는 아래 중 하나만 사용:
        - 후킹
        - 공감
        - 설명
        - 숫자정리
        - 해결책
        - 경고
        - 마무리

        ※ 기존 대본의 흐름을 보고 가장 가까운 목적 하나만 부여
        ※ 확실하지 않으면 설명 사용

        ------------------------------------------------------------
        [화면 핵심 요소 규칙]
        screen_core_elements 는 배열로 출력하고,
        아래 예시처럼 시각 요소 중심으로만 정리:
        - 인물
        - 시니어 남성
        - 시니어 여성
        - 의사
        - 음식
        - 식탁
        - 주방
        - 물컵
        - 약병
        - 심장 아이콘
        - 혈관 아이콘
        - 뇌 아이콘
        - 방패 아이콘
        - 숫자 그래픽
        - 체크리스트
        - 침대
        - 산책 장면
        - 스트레칭 장면

        ※ 실제 자막 문장 전체를 넣지 말고, 시각적으로 표현할 핵심 요소만 넣기
        ※ "텍스트"가 필요한 경우에도 실제 문구가 아니라 "강조 텍스트 영역", "숫자 그래픽"처럼 일반화할 것

        ------------------------------------------------------------
        [B-roll 성격 규칙]
        b_roll_type 은 아래 중 하나만 사용:
        - 실사형
        - 일러스트형
        - 인포그래픽형

        선택 기준:
        - 감정/일상/사례/공감: 실사형 또는 일러스트형
        - 건강 원리/숫자/구조 설명: 인포그래픽형
        - 시니어 건강 쇼츠 전체 톤상 애니메이션/일러스트 활용이 자연스러우면 일러스트형 우선 가능

        ------------------------------------------------------------
        [대체 컷 아이디어 규칙]
        - alt_cut_ideas 는 길이 2의 배열로 출력
        - 생성 실패 대비용 대체 시각 아이디어
        - 본 장면 목적과 같은 의미 범위 안에서만 변형
        - 새로운 메시지/의학 주장 추가 금지
        - 짧고 명확하게 작성

        예시:
        [
        "공원 벤치에 앉아 생각하는 시니어",
        "가족 사진을 바라보는 따뜻한 실내 장면"
        ]

        ------------------------------------------------------------
        [JSON 전체 메타 키]
        최상위 JSON에는 반드시 아래 키 포함:
        - title
        - target_audience
        - tone
        - cta
        - estimated_total_duration_sec
        - scenes

        값은 script_generation에 있으면 그대로 사용
        없으면 null 허용

        ------------------------------------------------------------
        [scenes 배열 - 각 scene 객체 필수 키]
        각 scene 객체에는 반드시 아래 키 포함:
        - scene_id
        - purpose
        - line_summary
        - screen_core_elements
        - duration_sec
        - b_roll_type
        - alt_cut_ideas
        - start_time
        - end_time
        - visual_focus
        - notes

        ------------------------------------------------------------
        [scene 값 생성 규칙]
        1) scene_id 는 "01", "02", "03" 처럼 2자리 문자열로 생성
        2) purpose 는 지정된 7개 분류 중 하나만 사용
        3) line_summary 는 해당 장면의 대사 내용을 짧게 요약
        4) screen_core_elements 는 배열
        5) duration_sec 는 장면 권장 길이(number)
        6) b_roll_type 은 지정된 3개 중 하나만 사용
        7) alt_cut_ideas 는 반드시 2개
        8) start_time / end_time 은 누적 시간으로 계산
        9) visual_focus 는 그 장면에서 가장 먼저 눈에 들어와야 하는 핵심 시각 포인트를 짧게 작성
        10) notes 는 연출 메모. 없으면 null 가능
        11) 총합 duration_sec 는 estimated_total_duration_sec 와 최대한 자연스럽게 맞출 것
        12) 기존 script_generation의 의미를 벗어나는 새로운 정보 추가 금지

        ------------------------------------------------------------
        [시간 계산 규칙]
        - 첫 장면 start_time = 0
        - 각 장면 end_time = start_time + duration_sec
        - 다음 장면 start_time = 이전 장면 end_time
        - 모든 시간은 초 단위 number
        - 소수점 사용 가능
        - 마지막 장면 end_time 이 estimated_total_duration_sec 와 약간 다를 수는 있으나, 가능한 한 맞출 것

        ------------------------------------------------------------
        [출력 형식 예외 금지]
        - JSON 코드블록 외 출력 금지
        - markdown 표 금지
        - 주석 금지
        - 설명 금지

        [최종 출력 형식]
        ```json
        {
        "title": "...",
        "target_audience": "...",
        "tone": "...",
        "cta": "...",
        "estimated_total_duration_sec": 0,
        "scenes": [
            {
            "scene_id": "01",
            "purpose": "후킹",
            "line_summary": "...",
            "screen_core_elements": ["..."],
            "duration_sec": 0,
            "b_roll_type": "일러스트형",
            "alt_cut_ideas": ["...", "..."],
            "start_time": 0,
            "end_time": 0,
            "visual_focus": "...",
            "notes": null
            }
        ]
        }

        """
    ).strip(),
    "image_prompt": textwrap.dedent(
        """
        {{scene_breakdown}}를 바탕으로 **이미지 생성 프롬프트용 JSON만** 생성해줘.
        (대본/장면표를 다시 만들지 말고, 이미지 프롬프트만 기존 scene 기준으로 구조화)

        [핵심 목표]
        - 시니어 건강 쇼츠에 최적화된 **애니메이션풍 일러스트(비실사)** 프롬프트 생성
        - 장면 목적에 맞는 스타일 선택 + 자막 가독성 높은 여백 확보
        - 썸네일은 CTR을 고려해 “한눈에 이해 + 신뢰 + 따뜻함” 중심으로 구성
        - 이미지 내부 텍스트는 절대 생성하지 않음(후편집 전제)

        [출력 요청]
        - 반드시 **JSON 코드블록으로만 출력**
        - 설명 / 주석 / 머리말 / 마무리 문장 / 표 / 일반 텍스트 출력 금지
        - JSON 문법 오류 절대 금지
        - 기존 scene 정보를 기준으로만 구조화
        - 새로운 대본/장면/메시지 창작 금지
        - 누락값이 있으면 null 사용 가능
        - scene 배열 순서 유지

        ------------------------------------------------------------
        [스타일 시스템 (TOP5)]
        scene의 purpose/의도에 맞게 아래 중 하나만 선택:

        1. SENIOR_LIFESTYLE
        - 따뜻한 시니어 일상 장면(산책, 식사, 대화, 휴식)

        2. MEDICAL_INFOGRAPHIC
        - 장기/혈관/뇌/건강 아이콘 기반 인포그래픽 설명

        3. DOCTOR_EXPLANATION
        - 친근한 의사가 설명하는 장면(권위 + 안심)

        4. SCIENCE_MEDICAL
        - 뇌/세포/혈관 등 과학적 설명용 일러스트(연구 느낌)

        5. HEALTHY_ACTION
        - 운동/식단/스트레칭/수면 등 실천 행동 장면(해결책)

        ------------------------------------------------------------
        [스타일 자동 선택 규칙]
        - 후킹 / 공감 / 사례: SENIOR_LIFESTYLE
        - 원리 설명 / 숫자 / 정보 전달: MEDICAL_INFOGRAPHIC
        - 전문가 조언 / 경고 / 안전수칙: DOCTOR_EXPLANATION
        - 연구 / 과학 근거: SCIENCE_MEDICAL
        - 실천 방법 / 해결책 / 루틴: HEALTHY_ACTION
        - 확실하지 않으면 SENIOR_LIFESTYLE 또는 MEDICAL_INFOGRAPHIC 중 더 단순한 쪽 선택

        ------------------------------------------------------------
        [최우선 스타일 규칙: 애니메이션풍 일러스트 전용]
        - 모든 프롬프트는 **애니메이션풍 일러스트(비실사)** 기준
        - 실사/포토리얼/사진풍 프롬프트 작성 금지
        - 영어 프롬프트에는 반드시 다음 취지를 포함:
        "anime-style illustration, stylized, non-photorealistic, clean composition"

        ------------------------------------------------------------
        [텍스트 렌더링 규칙]
        - 이미지 생성 프롬프트에 실제 문장/한글 문구 포함 금지
        - 텍스트는 후편집 전제
        - 영어 프롬프트에는 반드시 포함:
        "No text, no letters, no typography, no Korean characters rendered in the image"
        - 네거티브 프롬프트에는 반드시 포함:
        "text, letters, typography, caption, subtitle, Korean characters, Hangul, watermark, logo"

        ------------------------------------------------------------
        [자막 여백 규칙]
        - 각 장면 프롬프트에 반드시 "subtitle-safe negative space" 개념 반영
        - 여백 위치를 구체적으로 지정:
        "top third", "top right", "left margin", "bottom center" 등

        ------------------------------------------------------------
        [전역 톤/색감/조명]
        - 색감: beige / wood tone / white / soft pastel
        - 조명: soft natural light / warm ambient light / soft diffused lighting
        - 분위기: 공포 연출 금지, 생활 속 주의 + 안심 솔루션 톤 유지
        - 고어/혐오/과도한 의료 공포 표현 금지

        ------------------------------------------------------------
        [캐릭터 일관성 규칙 (필수)]
        - 전 장면에서 동일 캐릭터 유지(최소 1명, 가능하면 2명 고정)
        - 기본 캐릭터 예시(매 장면 공통 반영):
        - 70대 한국인 여성 또는 남성
        - 자연스러운 회색 머리
        - 온화한 표정
        - beige cardigan / light sweater / comfortable clothing
        - 장면이 바뀌어도 얼굴/헤어/의상 톤 유지
        - 과도한 미형/아이돌 느낌 금지
        - 캐릭터 정보가 scene_breakdown에 이미 있으면 기존 정보 우선, 없으면 위 기본 캐릭터 사용

        ------------------------------------------------------------
        [네거티브 프롬프트 필수 포함 요소]
        아래 요소를 negative_prompt에 반드시 포함:
        - text, letters, typography, caption, subtitle, Korean characters, Hangul, watermark, logo
        - photorealistic, realistic photo, live-action, DSLR, camera lens effect, photographic skin texture
        - gore, blood, surgery, horror, disturbing medical scene

        ------------------------------------------------------------
        [프롬프트 품질 규칙]
        각 프롬프트에는 아래 요소가 반영되어야 함:
        - shot type (close-up / medium / wide)
        - composition (좌/우 배치, 중앙 오브젝트 등)
        - background (단순)
        - lighting (부드럽고 따뜻)
        - subtitle-safe negative space + 위치
        - 배경 복잡도 낮게 유지
        - 이미지 안에 텍스트 생성 금지

        ------------------------------------------------------------
        [썸네일 전용 스타일 4종 (thumb_style_tag)]
        1. THUMB_HERO_PORTRAIT
        - 캐릭터 얼굴/상반신 중심 + 심플 배경 + 큰 여백

        2. THUMB_ICON_INFOGRAPHIC
        - 큰 건강 아이콘(뇌/혈관/심장 등) + 캐릭터 1명 + 단순 배경

        3. THUMB_BEFORE_AFTER
        - 좌/우 또는 상/하로 걱정→안심 대비(텍스트 없이 표정/색감으로만)

        4. THUMB_DOCTOR_TRUST
        - 의사 캐릭터 + 신뢰 소품(클립보드/스테토스코프) + 넓은 여백

        - 확실하지 않으면 THUMB_ICON_INFOGRAPHIC 우선

        ------------------------------------------------------------
        [JSON 전체 메타 키]
        최상위 JSON에는 반드시 아래 키 포함:
        - title
        - target_audience
        - tone
        - safety_notes
        - cta
        - estimated_total_duration_sec
        - character_consistency
        - scenes
        - thumbnails

        ------------------------------------------------------------
        [character_consistency 객체 필수 키]
        - main_character
        - support_character
        - wardrobe
        - hair
        - mood
        - continuity_rule

        값이 명확하지 않으면 null 허용하되, 가능하면 scene_breakdown 기준으로 채움

        ------------------------------------------------------------
        [scenes 배열 - 각 scene 객체 필수 키]
        각 scene 객체에는 반드시 아래 키 포함:
        - scene_id
        - purpose
        - duration_sec
        - start_time
        - end_time
        - style_tag
        - visual_type
        - aspect_ratio
        - subtitle_safe_area
        - character_consistency_note
        - image_prompt_ko
        - image_prompt_en
        - negative_prompt
        - alt_prompt_a_ko
        - alt_prompt_a_en
        - alt_prompt_b_ko
        - alt_prompt_b_en

        [scene 값 채우기 규칙]
        1) scene_id / purpose / duration_sec / start_time / end_time 은
        scene_breakdown에 있으면 그대로 반영
        2) visual_type 이 scene_breakdown에 있으면 그대로 사용, 없으면 style_tag와 가장 자연스럽게 맞는 값 사용
        3) aspect_ratio 는 무조건 "9:16"
        4) subtitle_safe_area 는 프롬프트 구성에 맞게 구체적으로 지정
        5) character_consistency_note 는 1~2줄 요약
        6) image_prompt_ko / image_prompt_en 은 실제 이미지 생성용으로 충분히 구체적으로 작성
        7) alt_prompt_a / alt_prompt_b 는 **같은 style_tag 안에서만 변형**
        8) 새로운 장면 내용/대사/의미 추가 금지

        ------------------------------------------------------------
        [thumbnails 배열 - 2개 객체 고정 생성]
        반드시 2개 생성:
        - thumbnail_id: "thumb_A"
        - thumbnail_id: "thumb_B"

        각 thumbnail 객체 필수 키:
        - thumbnail_id
        - purpose
        - thumb_style_tag
        - aspect_ratio
        - subtitle_safe_area
        - crop_safe_note
        - image_prompt_ko
        - image_prompt_en
        - negative_prompt

        [썸네일 생성 규칙]
        - 목적: CTR 최적화(한눈에 이해 / 신뢰 / 따뜻함)
        - 핵심 오브젝트 1개 + 캐릭터 1명(또는 최대 2명)
        - 배경은 매우 단순
        - 시선 유도 요소는 큰 아이콘/심볼 1개만
        - 표정은 걱정→안심 또는 친근한 미소
        - 자막 크게 넣을 여백 반드시 확보
        - 이미지 내부 텍스트 생성 금지
        - aspect_ratio 는 무조건 "9:16"
        - crop_safe_note 는 "중앙 인물/오브젝트 배치 권장" 취지로 작성
        - thumb_style_tag 는 위 4종 중 하나만 사용

        ------------------------------------------------------------
        [영어 프롬프트 공통 필수 포함 요소]
        모든 image_prompt_en / alt_prompt_*_en / thumbnail image_prompt_en 에 아래 취지가 반드시 반영되어야 함:
        - anime-style illustration
        - stylized
        - non-photorealistic
        - clean composition
        - No text, no letters, no typography, no Korean characters rendered in the image
        - subtitle-safe negative space

        ------------------------------------------------------------
        [출력 형식 예외 금지]
        - JSON 코드블록 외 출력 금지
        - markdown 표 금지
        - 주석 금지
        - 설명 금지

        [최종 출력 형식]
        ```json
        {
        "title": "...",
        "target_audience": "...",
        "tone": "...",
        "safety_notes": "...",
        "cta": "...",
        "estimated_total_duration_sec": 0,
        "character_consistency": {
            "main_character": "...",
            "support_character": "...",
            "wardrobe": "...",
            "hair": "...",
            "mood": "...",
            "continuity_rule": "..."
        },
        "scenes": [
            {
            "scene_id": "...",
            "purpose": "...",
            "duration_sec": 0,
            "start_time": 0,
            "end_time": 0,
            "style_tag": "...",
            "visual_type": "...",
            "aspect_ratio": "9:16",
            "subtitle_safe_area": "...",
            "character_consistency_note": "...",
            "image_prompt_ko": "...",
            "image_prompt_en": "...",
            "negative_prompt": "...",
            "alt_prompt_a_ko": "...",
            "alt_prompt_a_en": "...",
            "alt_prompt_b_ko": "...",
            "alt_prompt_b_en": "..."
            }
        ],
        "thumbnails": [
            {
            "thumbnail_id": "thumb_A",
            "purpose": "CTR 최적화",
            "thumb_style_tag": "...",
            "aspect_ratio": "9:16",
            "subtitle_safe_area": "...",
            "crop_safe_note": "...",
            "image_prompt_ko": "...",
            "image_prompt_en": "...",
            "negative_prompt": "..."
            },
            {
            "thumbnail_id": "thumb_B",
            "purpose": "CTR 최적화",
            "thumb_style_tag": "...",
            "aspect_ratio": "9:16",
            "subtitle_safe_area": "...",
            "crop_safe_note": "...",
            "image_prompt_ko": "...",
            "image_prompt_en": "...",
            "negative_prompt": "..."
            }
        ]
        }

        """
    ).strip(),
    "motion_subtitle_tts": textwrap.dedent(
        """
        {{scene_breakdown}} 와 {{script_generation}}을 기준으로  
        **카메라 모션 + 자막/TTS 설계 JSON만** 생성해줘.

        (이미지 프롬프트 생성 금지  
        FFmpeg JSON 생성 금지  
        장면 설계 변경 금지  
        기존 데이터를 구조화하는 단계)

        ------------------------------------------------------------

        [출력 요청]

        - 반드시 **JSON 코드블록으로만 출력**
        - 설명 / 주석 / 표 / 일반 텍스트 출력 금지
        - JSON 문법 오류 절대 금지
        - 기존 scene_breakdown 정보를 변경하지 말 것
        - 새로운 대본 생성 금지
        - script_generation의 script / subtitle_lines 기반으로만 작성

        ------------------------------------------------------------

        [목표]

        각 scene에 대해 아래 정보를 생성한다.

        1️⃣ 카메라 모션 설계  
        2️⃣ 자막 표시 설계  
        3️⃣ TTS 설정  

        이 데이터는 이후 단계에서 **FFmpeg 자동 편집 JSON 생성**에 사용된다.

        ------------------------------------------------------------

        [JSON 전체 메타 키]

        최상위 JSON에는 반드시 아래 키 포함

        - title
        - target_audience
        - tone
        - estimated_total_duration_sec
        - scenes

        값은 script_generation에 있으면 그대로 사용

        ------------------------------------------------------------

        [scene 객체 필수 키]

        각 scene 객체에는 반드시 아래 키 포함

        - scene_id
        - purpose
        - duration_sec
        - start_time
        - end_time

        ----------------------------

        [카메라 모션 관련 키]

        - framing_start
        - camera_motion
        - motion_duration_sec
        - motion_intensity
        - transition_to_next
        - visual_focus
        - subtitle_position

        값 규칙

        framing_start  
        다음 중 하나

        - wide
        - medium
        - close-up

        camera_motion

        - zoom-in
        - zoom-out
        - pan-left
        - pan-right
        - hold

        motion_duration_sec  
        scene duration 기준으로 자연스럽게 설정

        motion_intensity

        - weak
        - medium
        - strong

        transition_to_next

        - cut
        - fade
        - cross dissolve

        visual_focus  
        장면에서 가장 강조해야 할 시각 포인트

        subtitle_position

        - top
        - bottom
        - left
        - right

        ------------------------------------------------------------

        [자막 관련 키]

        - tts_text
        - subtitle_lines
        - highlight_keywords
        - highlight_timing_sec

        값 규칙

        tts_text  
        script_generation.script에서 해당 장면에 해당하는 문장

        subtitle_lines  
        배열 형태

        자막 규칙

        - 한 줄 12~18자
        - 최대 2줄
        - 시니어 가독성 우선
        - 호흡 단위로 끊기

        highlight_keywords

        배열

        예
        ["혈관 건강","아침 습관"]

        highlight_timing_sec

        숫자

        예

        1.2

        장면 시작 후 키워드 강조 타이밍

        ------------------------------------------------------------

        [TTS 설정 키 — 반드시 포함]

        - tts_provider
        - tts_voice
        - tts_rate
        - tts_pitch
        - tts_volume
        - tts_style
        - tts_styledegree
        - tts_output_filename
        - tts_ssml_optional

        ------------------------------------------------------------

        [TTS 기본값 규칙]

        scene_breakdown 또는 script_generation에  
        TTS 설정이 없으면 아래 기본값 사용

        tts_provider

        edge_tts

        tts_voice

        ko-KR-SunHiNeural

        tts_rate

        +10%

        tts_pitch

        0Hz

        tts_volume

        +0%

        tts_style

        general

        tts_styledegree

        1.0

        tts_output_filename

        {scene_id}_01.wav

        tts_ssml_optional

        null

        ------------------------------------------------------------

        [TTS 스타일 규칙]

        purpose 기반 최소 설정

        후킹 / 강조  
        serious

        공감 / 따뜻  
        calm

        설명 / 정보  
        general

        경고  
        serious

        확실하지 않으면

        general

        ------------------------------------------------------------

        [FFmpeg 구현 가능성 규칙]

        모션은 반드시 아래 범위 내에서만 제안

        zoompan 가능 모션

        zoom-in  
        zoom-out

        crop + pan 가능

        pan-left  
        pan-right

        정지

        hold

        전환

        cut  
        fade  
        cross dissolve

        ------------------------------------------------------------

        [주의]

        절대 하지 말 것

        - 새로운 대본 작성
        - 장면 추가
        - 이미지 프롬프트 생성
        - FFmpeg JSON 생성

        이 단계는 **모션 + 자막 + TTS 설계만 수행**

        ------------------------------------------------------------

        [최종 출력 예시 형식]

        ```json
        {
        "title": "...",
        "target_audience": "...",
        "tone": "...",
        "estimated_total_duration_sec": 55,
        "scenes": [
            {
            "scene_id": "01",
            "purpose": "후킹",
            "duration_sec": 5,
            "start_time": 0,
            "end_time": 5,

            "framing_start": "close-up",
            "camera_motion": "zoom-in",
            "motion_duration_sec": 5,
            "motion_intensity": "weak",
            "transition_to_next": "cut",
            "visual_focus": "시니어 표정",
            "subtitle_position": "bottom",

            "tts_text": "...",
            "subtitle_lines": [
                "...",
                "..."
            ],
            "highlight_keywords": [
                "..."
            ],
            "highlight_timing_sec": 1.2,

            "tts_provider": "edge_tts",
            "tts_voice": "ko-KR-SunHiNeural",
            "tts_rate": "+10%",
            "tts_pitch": "0Hz",
            "tts_volume": "+0%",
            "tts_style": "general",
            "tts_styledegree": 1.0,
            "tts_output_filename": "01_01.wav",
            "tts_ssml_optional": null
            }
        ]
        }

        """
    ).strip(),
    "ffmpeg_json": textwrap.dedent(
        """
        {{scene_breakdown}}, {{image_prompt}}, {{motion_subtitle_tts}} 를 바탕으로  
        **FFmpeg / 자동편집용 최종 JSON만** 생성해줘.

        (새로운 대본, 새로운 프롬프트, 새로운 장면, 새로운 키워드 창작 금지  
        기존 JSON 자료를 충돌 없이 정확히 병합/구조화하는 작업만 수행)

        ------------------------------------------------------------
        [출력 요청]

        - 반드시 **JSON 코드블록으로만 출력**
        - 설명 / 주석 / 표 / 일반 텍스트 / 머리말 / 마무리 금지
        - JSON 문법 오류 절대 금지
        - 숫자 필드는 반드시 number 타입
        - 문자열/배열/object 타입 엄격히 유지
        - scenes 배열 순서 유지

        ------------------------------------------------------------
        [병합 원칙]

        입력 JSON 3개를 아래 우선순위로 병합:

        1. motion_subtitle_tts
        - TTS, 자막, 모션, 전환 관련 값 최우선

        2. image_prompt
        - 이미지 프롬프트, 비주얼 스타일, 네거티브 프롬프트, 썸네일/화면비 관련 값 반영

        3. scene_breakdown
        - 장면 목적, 시각 포커스, duration_sec, start_time, end_time, visual_type, keywords 등 기본 장면 구조 반영

        ※ 같은 의미의 값이 여러 입력에 중복되면 위 우선순위를 따른다.
        ※ 누락값만 하위 입력에서 보충한다.
        ※ 값 충돌이 있어도 새로운 의미를 창작하지 말고 기존 정보 안에서만 정리할 것.

        ------------------------------------------------------------
        [출력 목표]

        최종 JSON은 FFmpeg / 자동 편집 파이프라인에서 바로 사용할 수 있어야 한다.

        이 JSON은 아래를 한 번에 담는 최종 렌더 기준 데이터다:

        - 장면 타이밍
        - 이미지 프롬프트
        - 카메라 모션
        - 자막
        - TTS 설정
        - 전환
        - 렌더용 화면비
        - 선택적 SFX/BGM 메모

        ------------------------------------------------------------
        [최상위 JSON 필수 키]

        반드시 아래 키 포함:

        - title
        - target_audience
        - tone
        - safety_notes
        - cta
        - estimated_total_duration_sec
        - aspect_ratio
        - render_style
        - scenes

        ------------------------------------------------------------
        [최상위 값 규칙]

        title
        - 입력 자료에 있는 값 사용
        - 없으면 null

        target_audience
        - 입력 자료에 있는 값 사용
        - 없으면 null

        tone
        - 입력 자료에 있는 값 사용
        - 없으면 null

        safety_notes
        - 입력 자료에 있는 값 사용
        - 없으면 null

        cta
        - 입력 자료에 있는 값 사용
        - 없으면 null

        estimated_total_duration_sec
        - 입력 자료 값 사용
        - 반드시 number

        aspect_ratio
        - 기본값 "9:16"

        render_style
        - 기본값 "ffmpeg_auto_edit"

        ------------------------------------------------------------
        [scene 객체 필수 키]

        각 scene 객체에는 반드시 아래 키 포함:

        - scene_id
        - purpose
        - duration_sec
        - start_time
        - end_time

        - keywords
        - visual_type
        - visual_focus

        - image_prompt_ko
        - image_prompt_en
        - negative_prompt
        - aspect_ratio
        - image_output_filename

        - tts_text
        - subtitle_lines
        - overlay_text
        - overlay_position
        - subtitle_style_preset

        - camera_motion
        - transition_to_next

        - tts_provider
        - tts_voice
        - tts_rate
        - tts_pitch
        - tts_volume
        - tts_style
        - tts_styledegree
        - tts_output_filename
        - tts_ssml_optional

        - sfx_optional
        - bgm_mood_optional

        ------------------------------------------------------------
        [scene 객체 세부 규칙]

        scene_id
        - "01", "02" 같은 2자리 문자열 유지
        - 기존 자료 값 우선

        purpose
        - scene_breakdown 기준 우선
        - 없으면 motion_subtitle_tts 값 사용
        - 없으면 null

        duration_sec / start_time / end_time
        - scene_breakdown 기준 우선
        - motion_subtitle_tts에 더 명확한 값이 있으면 그것을 사용
        - 반드시 number

        keywords
        - scene_breakdown에 있으면 사용
        - 없으면 빈 배열 [] 허용
        - 새로운 키워드 창작 금지

        visual_type
        - scene_breakdown 또는 image_prompt 값 사용
        - 없으면 null

        visual_focus
        - scene_breakdown 또는 motion_subtitle_tts 값 사용
        - 없으면 null

        ------------------------------------------------------------
        [이미지 관련 값 규칙]

        image_prompt_ko
        - image_prompt.scenes 기준 사용

        image_prompt_en
        - image_prompt.scenes 기준 사용

        negative_prompt
        - image_prompt.scenes 기준 사용

        aspect_ratio
        - scene 단위 기본값 "9:16"

        image_output_filename
        - 기본값: "{scene_id}.png"
        - 예: "01.png", "02.png"
        - 기존에 파일명이 있으면 기존 값 우선

        ------------------------------------------------------------
        [자막 관련 값 규칙]

        tts_text
        - motion_subtitle_tts 기준 사용
        - 없으면 해당 scene의 script 기반 내용 사용 가능
        - 단, 새로운 문장 창작 금지

        subtitle_lines
        - motion_subtitle_tts 기준 사용
        - 배열 유지
        - 최대 2줄 기준이 이미 있으면 그대로 유지

        overlay_text
        - 실제 영상 위에 표시할 자막 데이터
        - 기본적으로 subtitle_lines 와 동일한 값 사용
        - 반드시 배열 형태 유지
        - 새로운 문구 생성 금지

        overlay_position
        - motion_subtitle_tts.subtitle_position 기준 사용
        - 값은 아래 중 하나로 정규화:
        - top
        - bottom
        - left
        - right
        - center
        - 없으면 "bottom"

        subtitle_style_preset
        - 기본값 "senior_readable_default"
        - 기존 값 있으면 우선 사용

        ------------------------------------------------------------
        [카메라 모션 관련 값 규칙]

        camera_motion 은 반드시 object 형태로 출력:

        - framing_start
        - motion_type
        - motion_duration_sec
        - motion_intensity
        - visual_focus

        예:
        {
        "framing_start": "close-up",
        "motion_type": "zoom-in",
        "motion_duration_sec": 4.5,
        "motion_intensity": "weak",
        "visual_focus": "시니어 표정"
        }

        값 규칙:
        - framing_start: wide / medium / close-up
        - motion_type: zoom-in / zoom-out / pan-left / pan-right / hold
        - motion_duration_sec: number
        - motion_intensity: weak / medium / strong
        - visual_focus: 기존 자료 값 사용

        ※ 기존 입력에서 camera_motion이 문자열 하나로만 있더라도,
        최종 JSON에서는 반드시 위 object 구조로 정리할 것.
        ※ 새로운 연출 창작 금지, 기존 motion_subtitle_tts 값을 구조화만 할 것.

        ------------------------------------------------------------
        [전환 관련 값 규칙]

        transition_to_next
        - 다음 중 하나:
        - cut
        - fade
        - cross dissolve
        - motion_subtitle_tts 값 우선
        - 없으면 "cut"

        ------------------------------------------------------------
        [EdgeTTS 설정 키 — 반드시 포함]

        - tts_provider
        - tts_voice
        - tts_rate
        - tts_pitch
        - tts_volume
        - tts_style
        - tts_styledegree
        - tts_output_filename
        - tts_ssml_optional

        ------------------------------------------------------------
        [EdgeTTS 설정 규칙]

        1) 기존 자료에 씬별 음성 설정 정보가 있으면 그대로 반영

        2) 기존 자료에 없으면 아래 기본값 사용
        - tts_provider: "edge_tts"
        - tts_voice: "ko-KR-SunHiNeural"
        - tts_rate: "+10%"
        - tts_pitch: "0Hz"
        - tts_volume: "+0%"
        - tts_style: "general"
        - tts_styledegree: 1.0
        - tts_output_filename: "{scene_id}_01.wav"
        - tts_ssml_optional: null

        3) tts_text는 절대 수정하지 말 것

        4) 감정 스타일 값은 새로 창작하지 말고 기존 tone/purpose에 명시적으로 부합하는 최소 일반값만 사용
        - 후킹/강조: "serious" 또는 "cheerful"
        - 안전수칙/경고: "serious"
        - 공감/따뜻: "calm"
        - 근거/설명: "general"
        - 확실하지 않으면 "general"

        ------------------------------------------------------------
        [SFX / BGM 값 규칙]

        sfx_optional
        - 기존 자료에 있으면 사용
        - 없으면 null

        bgm_mood_optional
        - 기존 자료에 있으면 사용
        - 없으면 tone/purpose와 충돌 없는 일반값 사용 가능:
        - "warm"
        - "calm"
        - "gentle informative"
        - 다만 확실하지 않으면 null

        ------------------------------------------------------------
        [누락값 처리 규칙]

        - 문자열 누락: null
        - 배열 누락: []
        - object 누락: null 또는 기본 object
        - 숫자 누락: 가능한 경우 기존 자료에서 계산, 아니면 null
        - 새로운 의미/메시지/의학 정보 창작 금지

        ------------------------------------------------------------
        [최종 출력 형식]

        ```json
        {
        "title": "...",
        "target_audience": "...",
        "tone": "...",
        "safety_notes": "...",
        "cta": "...",
        "estimated_total_duration_sec": 55,
        "aspect_ratio": "9:16",
        "render_style": "ffmpeg_auto_edit",
        "scenes": [
            {
            "scene_id": "01",
            "purpose": "후킹",
            "duration_sec": 4.5,
            "start_time": 0,
            "end_time": 4.5,

            "keywords": ["..."],
            "visual_type": "...",
            "visual_focus": "...",

            "image_prompt_ko": "...",
            "image_prompt_en": "...",
            "negative_prompt": "...",
            "aspect_ratio": "9:16",
            "image_output_filename": "01.png",

            "tts_text": "...",
            "subtitle_lines": ["...", "..."],
            "overlay_text": ["...", "..."],
            "overlay_position": "bottom",
            "subtitle_style_preset": "senior_readable_default",

            "camera_motion": {
                "framing_start": "close-up",
                "motion_type": "zoom-in",
                "motion_duration_sec": 4.5,
                "motion_intensity": "weak",
                "visual_focus": "..."
            },
            "transition_to_next": "cut",

            "tts_provider": "edge_tts",
            "tts_voice": "ko-KR-SunHiNeural",
            "tts_rate": "+10%",
            "tts_pitch": "0Hz",
            "tts_volume": "+0%",
            "tts_style": "general",
            "tts_styledegree": 1.0,
            "tts_output_filename": "01_01.wav",
            "tts_ssml_optional": null,

            "sfx_optional": null,
            "bgm_mood_optional": null
            }
        ]
        }

        """
    ).strip(),
}


@dataclass
class Node:
    key: str
    name: str
    depends_on: List[str] = field(default_factory=list)
    state_key: Optional[str] = None
    prompt_key: Optional[str] = None


@dataclass
class TokenMeta:
    token: str
    display: str
    node_key: str
    path: List[Any]
    kind: str
    depth: int
    is_whole_node: bool = False


@dataclass
class GroupState:
    expanded: bool = True


NODES: List[Node] = [
    Node("content_input", "1) 내용입력 노드", [], "content_input", None),
    Node("script_generation", "2) 대본생성 노드", ["content_input"], "script_generation", "script_generation"),
    Node("scene_breakdown", "3) 장면분해 노드", ["script_generation"], "scene_breakdown", "scene_breakdown"),
    Node("image_prompt", "4) 이미지생성프롬프트 노드", ["scene_breakdown"], "image_prompt", "image_prompt"),
    Node(
        "motion_subtitle_tts",
        "5) 쇼츠 카메라 모션 + 자막/TTS 분리 노드",
        ["script_generation", "scene_breakdown"],
        "motion_subtitle_tts",
        "motion_subtitle_tts",
    ),
    Node(
        "ffmpeg_json",
        "6) ffmpeg용 JSON 생성 최종노드",
        ["scene_breakdown", "image_prompt", "motion_subtitle_tts"],
        "ffmpeg_json",
        "ffmpeg_json",
    ),
]

NODE_MAP: Dict[str, Node] = {node.key: node for node in NODES}

# {{ ... }} 내부 전체 표현식 추출
TOKEN_PATTERN = re.compile(r"\{\{\s*(.*?)\s*\}\}")
# path segment용
SEGMENT_PATTERN = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)(\[[0-9]+\])*")
INDEX_PATTERN = re.compile(r"\[([0-9]+)\]")


class TokenResolver:
    def __init__(self, node_map: Dict[str, Node]):
        self.node_map = node_map

    @staticmethod
    def stringify_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        if value is None:
            return ""
        return str(value)

    def parse_token(self, token_expr: str) -> Tuple[bool, Dict[str, Any], str]:
        expr = token_expr.strip()
        if not expr:
            return False, {}, "빈 토큰입니다."

        first_part_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)", expr)
        if not first_part_match:
            return False, {}, f"잘못된 토큰 문법입니다: {expr}"

        node_key = first_part_match.group(1)
        if node_key not in self.node_map:
            return False, {}, f"존재하지 않는 노드입니다: {node_key}"

        rest = expr[len(node_key):]
        path: List[Any] = []

        while rest:
            if rest.startswith("."):
                rest = rest[1:]
                seg_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)", rest)
                if not seg_match:
                    return False, {}, f"잘못된 필드 경로입니다: {expr}"
                field_name = seg_match.group(1)
                path.append(field_name)
                rest = rest[len(field_name):]

                while rest.startswith("["):
                    idx_match = re.match(r"^\[([0-9]+)\]", rest)
                    if not idx_match:
                        return False, {}, f"잘못된 배열 인덱스 문법입니다: {expr}"
                    path.append(int(idx_match.group(1)))
                    rest = rest[len(idx_match.group(0)):]
            elif rest.startswith("["):
                idx_match = re.match(r"^\[([0-9]+)\]", rest)
                if not idx_match:
                    return False, {}, f"잘못된 배열 인덱스 문법입니다: {expr}"
                path.append(int(idx_match.group(1)))
                rest = rest[len(idx_match.group(0)):]
            else:
                return False, {}, f"잘못된 토큰 문법입니다: {expr}"

        return True, {"node_key": node_key, "path": path, "expr": expr}, ""

    def get_value_by_path(self, root_value: Any, path: List[Any], token_expr_for_error: str) -> Any:
        current = root_value
        current_path = ""

        for step in path:
            if isinstance(step, str):
                current_path = f"{current_path}.{step}" if current_path else step
                if not isinstance(current, dict):
                    raise KeyError(f"dict가 아닌 값에서 필드를 참조했습니다: {token_expr_for_error}")
                if step not in current:
                    raise KeyError(f"존재하지 않는 필드입니다: {token_expr_for_error}")
                current = current[step]
            elif isinstance(step, int):
                current_path = f"{current_path}[{step}]"
                if not isinstance(current, list):
                    raise KeyError(f"list가 아닌 값에서 인덱스를 참조했습니다: {token_expr_for_error}")
                if step < 0 or step >= len(current):
                    raise IndexError(f"배열 인덱스가 유효하지 않습니다: {token_expr_for_error}")
                current = current[step]
            else:
                raise KeyError(f"지원하지 않는 경로 타입입니다: {token_expr_for_error}")

        return current

    def resolve_token(self, token_expr: str, state_data: Dict[str, Any]) -> Any:
        ok, parsed, msg = self.parse_token(token_expr)
        if not ok:
            raise ValueError(msg)

        node_key = parsed["node_key"]
        path = parsed["path"]

        if node_key not in state_data:
            raise KeyError(f"참조한 노드 결과가 없습니다: {node_key}")

        root_value = state_data[node_key]
        return self.get_value_by_path(root_value, path, token_expr)

    def validate_token(
        self,
        token_expr: str,
        current_node_key: str,
        app: "PreviewFlowApp",
        require_completed: bool = True,
        require_value: bool = True,
    ) -> Tuple[bool, str]:
        ok, parsed, msg = self.parse_token(token_expr)
        if not ok:
            return False, msg

        node_key = parsed["node_key"]
        allowed_prev = {node.key for node in app.get_previous_nodes(current_node_key)}

        if node_key not in allowed_prev:
            return False, f"{current_node_key} 노드에서는 이전 노드만 참조할 수 있습니다: {token_expr}"

        if require_completed and not app.is_completed(node_key):
            return False, f"완료되지 않은 노드를 참조하고 있습니다: {node_key}"

        if require_value:
            value = app._get_node_value(node_key)
            if value is None or value == "":
                return False, f"참조한 노드의 결과가 비어 있습니다: {node_key}"

        try:
            if require_value:
                self.resolve_token(token_expr, app.state.get("data", {}))
            else:
                root_value = app._get_node_value(node_key)
                if root_value not in (None, ""):
                    self.get_value_by_path(root_value, parsed["path"], token_expr)
        except Exception as exc:
            return False, str(exc)

        return True, ""


class NodeFieldExplorer:
    def __init__(self, max_depth: int = 4, include_list_sample: bool = True):
        self.max_depth = max_depth
        self.include_list_sample = include_list_sample

    def build_tokens_for_node(self, node_key: str, node_value: Any) -> List[TokenMeta]:
        tokens: List[TokenMeta] = []

        tokens.append(
            TokenMeta(
                token=f"{{{{{node_key}}}}}",
                display="전체",
                node_key=node_key,
                path=[],
                kind="node",
                depth=0,
                is_whole_node=True,
            )
        )

        self._explore_value(
            node_key=node_key,
            value=node_value,
            tokens=tokens,
            current_path=[],
            depth=1,
        )
        return tokens

    def _token_expr(self, node_key: str, path: List[Any]) -> str:
        expr = node_key
        for p in path:
            if isinstance(p, str):
                expr += f".{p}"
            else:
                expr += f"[{p}]"
        return f"{{{{{expr}}}}}"

    def _display_name(self, path: List[Any], is_whole_node: bool = False) -> str:
        if is_whole_node:
            return "전체"
        if not path:
            return "전체"

        expr = ""
        for i, p in enumerate(path):
            if isinstance(p, str):
                if i == 0:
                    expr += p
                else:
                    expr += f".{p}"
            else:
                expr += f"[{p}]"
        return expr

    def _append_token(
        self,
        tokens: List[TokenMeta],
        node_key: str,
        path: List[Any],
        kind: str,
        depth: int,
    ) -> None:
        tokens.append(
            TokenMeta(
                token=self._token_expr(node_key, path),
                display=self._display_name(path),
                node_key=node_key,
                path=path[:],
                kind=kind,
                depth=depth,
                is_whole_node=False,
            )
        )

    def _explore_value(
        self,
        node_key: str,
        value: Any,
        tokens: List[TokenMeta],
        current_path: List[Any],
        depth: int,
    ) -> None:
        if depth > self.max_depth:
            return

        if isinstance(value, dict):
            for key, sub_value in value.items():
                new_path = current_path + [key]
                self._append_token(tokens, node_key, new_path, "field", depth)
                self._explore_value(node_key, sub_value, tokens, new_path, depth + 1)

        elif isinstance(value, list):
            self._append_token(tokens, node_key, current_path, "list", depth - 1 if depth > 0 else 0)

            if self.include_list_sample and value:
                sample_index = 0
                sample_path = current_path + [sample_index]
                self._append_token(tokens, node_key, sample_path, "list_item", depth)
                self._explore_value(node_key, value[sample_index], tokens, sample_path, depth + 1)


class DragManager:
    def __init__(self, root: tk.Misc):
        self.root = root
        self.dragging = False
        self.drag_token: Optional[str] = None
        self.drag_source_widget: Optional[tk.Widget] = None
        self.ghost: Optional[tk.Toplevel] = None
        self.start_x_root = 0
        self.start_y_root = 0
        self.threshold = 6
        self.drop_targets: List[tk.Text] = []
        self.default_insert_callback: Optional[Callable[[str], None]] = None

    def register_text_target(self, text_widget: tk.Text) -> None:
        if text_widget not in self.drop_targets:
            self.drop_targets.append(text_widget)

    def unregister_text_target(self, text_widget: tk.Text) -> None:
        if text_widget in self.drop_targets:
            self.drop_targets.remove(text_widget)

    def set_default_insert_callback(self, callback: Callable[[str], None]) -> None:
        self.default_insert_callback = callback

    def begin_candidate(self, widget: tk.Widget, token_value: str, event: tk.Event) -> None:
        self.dragging = False
        self.drag_token = token_value
        self.drag_source_widget = widget
        self.start_x_root = event.x_root
        self.start_y_root = event.y_root

    def on_motion(self, event: tk.Event) -> None:
        if not self.drag_token:
            return

        dx = abs(event.x_root - self.start_x_root)
        dy = abs(event.y_root - self.start_y_root)

        if not self.dragging and (dx >= self.threshold or dy >= self.threshold):
            self._start_drag_visual(event.x_root, event.y_root)

        if self.dragging:
            self._move_ghost(event.x_root, event.y_root)

    def on_release(self, event: tk.Event) -> bool:
        if not self.drag_token:
            self.cancel_drag()
            return False

        inserted = False
        if self.dragging:
            inserted = self._drop_at(event.x_root, event.y_root)

        self.cancel_drag()
        return inserted

    def _start_drag_visual(self, x_root: int, y_root: int) -> None:
        self.dragging = True
        if self.ghost is not None:
            try:
                self.ghost.destroy()
            except Exception:
                pass

        self.ghost = tk.Toplevel(self.root)
        self.ghost.overrideredirect(True)
        self.ghost.attributes("-topmost", True)
        try:
            self.ghost.attributes("-alpha", 0.92)
        except Exception:
            pass

        label = tk.Label(
            self.ghost,
            text=self.drag_token,
            bg="#2b2f36",
            fg="white",
            bd=1,
            relief="solid",
            padx=8,
            pady=4,
            font=("Malgun Gothic", 9, "bold"),
        )
        label.pack()
        self._move_ghost(x_root, y_root)

    def _move_ghost(self, x_root: int, y_root: int) -> None:
        if self.ghost is None:
            return
        self.ghost.geometry(f"+{x_root + 12}+{y_root + 12}")

    def _resolve_text_target(self, x_root: int, y_root: int) -> Optional[tk.Text]:
        widget = self.root.winfo_containing(x_root, y_root)
        while widget is not None:
            if isinstance(widget, tk.Text):
                return widget
            widget = widget.master
        return None

    def _drop_at(self, x_root: int, y_root: int) -> bool:
        text_widget = self._resolve_text_target(x_root, y_root)
        if text_widget is None:
            return False

        try:
            local_x = x_root - text_widget.winfo_rootx()
            local_y = y_root - text_widget.winfo_rooty()
            index = text_widget.index(f"@{local_x},{local_y}")
            text_widget.mark_set("insert", index)
            text_widget.insert(index, self.drag_token)
            text_widget.focus_set()
            return True
        except Exception:
            try:
                text_widget.insert("insert", self.drag_token)
                text_widget.focus_set()
                return True
            except Exception:
                if self.default_insert_callback is not None:
                    self.default_insert_callback(self.drag_token)
                    return True
        return False

    def cancel_drag(self) -> None:
        self.dragging = False
        self.drag_token = None
        self.drag_source_widget = None
        if self.ghost is not None:
            try:
                self.ghost.destroy()
            except Exception:
                pass
        self.ghost = None


class TokenChip(tk.Label):
    def __init__(
        self,
        master: tk.Misc,
        token_meta: TokenMeta,
        insert_callback: Callable[[str], None],
        drag_manager: Optional[DragManager] = None,
        **kwargs: Any,
    ):
        self.token_meta = token_meta
        self.insert_callback = insert_callback
        self.drag_manager = drag_manager

        bg = "#2f5bea" if token_meta.is_whole_node else "#e8edf6"
        fg = "white" if token_meta.is_whole_node else "#1f2937"
        active_bg = "#2447b9" if token_meta.is_whole_node else "#d6dfef"
        bd_color = "#1d4ed8" if token_meta.is_whole_node else "#b8c2d6"

        super().__init__(
            master,
            text=token_meta.display,
            bg=bg,
            fg=fg,
            bd=1,
            relief="solid",
            padx=10,
            pady=4,
            cursor="hand2",
            font=("Malgun Gothic", 9, "bold" if token_meta.is_whole_node else "normal"),
            **kwargs,
        )

        self.normal_bg = bg
        self.normal_fg = fg
        self.active_bg = active_bg
        self.border_color = bd_color
        self.configure(highlightthickness=0)

        self._pressed = False
        self._drag_inserted = False

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_enter(self, event=None) -> None:
        self.configure(bg=self.active_bg)

    def _on_leave(self, event=None) -> None:
        if not self._pressed:
            self.configure(bg=self.normal_bg)

    def _on_press(self, event: tk.Event) -> None:
        self._pressed = True
        self._drag_inserted = False
        self.configure(bg=self.active_bg)

        if self.drag_manager is not None:
            self.drag_manager.begin_candidate(self, self.token_meta.token, event)

    def _on_motion(self, event: tk.Event) -> None:
        if self.drag_manager is not None:
            self.drag_manager.on_motion(event)

    def _on_release(self, event: tk.Event) -> None:
        inserted_by_drag = False
        if self.drag_manager is not None:
            inserted_by_drag = self.drag_manager.on_release(event)

        if not inserted_by_drag:
            self.insert_callback(self.token_meta.token)

        self._pressed = False
        self.configure(bg=self.normal_bg)


class TokenPanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        app: "PreviewFlowApp",
        drag_manager: Optional[DragManager],
        insert_callback: Callable[[str], None],
        current_node_key_getter: Callable[[], str],
        title_text: str = "참조 패널",
    ):
        super().__init__(master)
        self.app = app
        self.drag_manager = drag_manager
        self.insert_callback = insert_callback
        self.current_node_key_getter = current_node_key_getter
        self.title_text = title_text
        self.group_states: Dict[str, GroupState] = {}

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    def destroy(self) -> None:
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        super().destroy()

    def _on_inner_configure(self, event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event=None) -> None:
        try:
            width = self.canvas.winfo_width()
            self.canvas.itemconfigure(self.inner_window, width=width)
        except Exception:
            pass

    def _on_mousewheel(self, event) -> None:
        if not self.winfo_exists():
            return
        try:
            widget_under_mouse = self.winfo_containing(event.x_root, event.y_root)
            if widget_under_mouse is None:
                return
            parent = widget_under_mouse
            inside_self = False
            while parent is not None:
                if parent == self:
                    inside_self = True
                    break
                parent = parent.master
            if not inside_self:
                return
        except Exception:
            return

        delta = -1 * int(event.delta / 120) if event.delta else 0
        if delta != 0:
            self.canvas.yview_scroll(delta, "units")

    def toggle_group(self, node_key: str) -> None:
        state = self.group_states.setdefault(node_key, GroupState(expanded=True))
        state.expanded = not state.expanded
        self.refresh()

    def refresh(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()

        current_node_key = self.current_node_key_getter()
        previous_nodes = self.app.get_previous_nodes(current_node_key)

        if not previous_nodes:
            ttk.Label(self.inner, text="이전 노드 없음").pack(anchor="w", padx=8, pady=8)
            return

        explorer = NodeFieldExplorer(max_depth=4, include_list_sample=True)

        for node in previous_nodes:
            group_frame = ttk.Frame(self.inner)
            group_frame.pack(fill="x", padx=6, pady=(6, 2))

            state = self.group_states.setdefault(node.key, GroupState(expanded=True))
            arrow = "▼" if state.expanded else "▶"

            header = tk.Frame(group_frame, bg="#f3f4f6", bd=1, relief="solid")
            header.pack(fill="x")

            header_label = tk.Label(
                header,
                text=f"{arrow} {node.key}",
                anchor="w",
                bg="#f3f4f6",
                fg="#111827",
                padx=8,
                pady=6,
                font=("Malgun Gothic", 10, "bold"),
                cursor="hand2",
            )
            header_label.pack(fill="x")

            header_label.bind("<Button-1>", lambda e, k=node.key: self.toggle_group(k))
            header.bind("<Button-1>", lambda e, k=node.key: self.toggle_group(k))

            if not state.expanded:
                continue

            body = ttk.Frame(group_frame)
            body.pack(fill="x", padx=4, pady=(4, 2))

            node_value = self.app._get_node_value(node.key)
            tokens = explorer.build_tokens_for_node(node.key, node_value)

            chip_wrap = tk.Frame(body, bg="white")
            chip_wrap.pack(fill="x", expand=True)

            self._pack_chip_wrap(chip_wrap, tokens)

    def _pack_chip_wrap(self, parent: tk.Frame, tokens: List[TokenMeta]) -> None:
        row = tk.Frame(parent, bg="white")
        row.pack(fill="x", anchor="w")

        parent.update_idletasks()
        max_width = max(parent.winfo_width(), 260)
        used_width = 0

        for token_meta in tokens:
            chip = TokenChip(
                row,
                token_meta=token_meta,
                insert_callback=self.insert_callback,
                drag_manager=self.drag_manager,
            )
            chip.update_idletasks()
            chip_w = max(chip.winfo_reqwidth(), 50) + 8

            if used_width + chip_w > max_width and used_width > 0:
                row = tk.Frame(parent, bg="white")
                row.pack(fill="x", anchor="w", pady=(4, 0))
                used_width = 0

            chip.pack(side="left", padx=4, pady=4, anchor="w")
            used_width += chip_w


class PreviewFlowApp:
    def __init__(self, session_path: Path, output_path: Path):
        self.session_path = session_path
        self.output_path = output_path
        self.token_resolver = TokenResolver(NODE_MAP)

        self.state: Dict[str, Any] = {
            "meta": {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            "prompts": DEFAULT_PROMPTS.copy(),
            "data": {},
            "completed_nodes": [],
        }

    # ---------- persistence ----------
    def load(self) -> None:
        if not self.session_path.exists():
            return

        raw = json.loads(self.session_path.read_text(encoding="utf-8"))
        self.state.update(raw)

        if "prompts" not in self.state:
            self.state["prompts"] = DEFAULT_PROMPTS.copy()

        for k, v in DEFAULT_PROMPTS.items():
            self.state["prompts"].setdefault(k, v)

        self.state.setdefault("data", {})
        self.state.setdefault("completed_nodes", [])
        self.state.setdefault("meta", {})

    def save(self) -> None:
        self.state["meta"]["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.session_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def reset_session(self) -> None:
        self.state = {
            "meta": {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            "prompts": DEFAULT_PROMPTS.copy(),
            "data": {},
            "completed_nodes": [],
        }
        self.save()
        if self.output_path.exists():
            self.output_path.unlink()

    # ---------- node status ----------
    def is_completed(self, node_key: str) -> bool:
        return node_key in self.state["completed_nodes"]

    def mark_completed(self, node_key: str) -> None:
        if node_key not in self.state["completed_nodes"]:
            self.state["completed_nodes"].append(node_key)

    def unmark_completed(self, node_key: str) -> None:
        if node_key in self.state["completed_nodes"]:
            self.state["completed_nodes"].remove(node_key)

    def can_run(self, node: Node) -> bool:
        return all(self.is_completed(dep) for dep in node.depends_on)

    def get_previous_nodes(self, current_node_key: str) -> List[Node]:
        result = []
        for node in NODES:
            if node.key == current_node_key:
                break
            result.append(node)
        return result

    # ---------- helpers ----------
    @staticmethod
    def _to_pretty_json_or_text(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    @staticmethod
    def _safe_parse_json(raw: str) -> Any:
        raw = raw.strip()
        if not raw:
            return ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def _get_node_value(self, node_key: str) -> Any:
        return self.state["data"].get(node_key, None)

    def extract_tokens(self, template: str) -> List[str]:
        raw_tokens = TOKEN_PATTERN.findall(template)
        result: List[str] = []
        seen = set()
        for token in raw_tokens:
            normalized = token.strip()
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    def validate_template_tokens(
        self,
        current_node_key: str,
        template_text: str,
        require_completed: bool = True,
        require_value: bool = True,
    ) -> Tuple[bool, str]:
        tokens = self.extract_tokens(template_text)
        if not tokens:
            return True, ""

        for token_expr in tokens:
            ok, msg = self.token_resolver.validate_token(
                token_expr=token_expr,
                current_node_key=current_node_key,
                app=self,
                require_completed=require_completed,
                require_value=require_value,
            )
            if not ok:
                return False, msg

        return True, ""

    def render_prompt(self, node: Node, template_override: Optional[str] = None) -> str:
        if not node.prompt_key:
            return ""

        template = template_override if template_override is not None else self.state["prompts"][node.prompt_key]

        def replace_token(match: re.Match) -> str:
            token_expr = match.group(1).strip()
            value = self.token_resolver.resolve_token(token_expr, self.state.get("data", {}))
            return self.token_resolver.stringify_value(value)

        return TOKEN_PATTERN.sub(replace_token, template)

    def save_output_file_if_ffmpeg(self) -> None:
        if "ffmpeg_json" not in self.state["data"]:
            return
        self.output_path.write_text(
            json.dumps(self.state["data"]["ffmpeg_json"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class PromptEditorDialog(tk.Toplevel):
    def __init__(self, master: "PreviewFlowGUI", app: PreviewFlowApp):
        super().__init__(master.root)
        self.master_gui = master
        self.app = app
        self.drag_manager = DragManager(self)

        self.title("프롬프트 템플릿 편집")
        self.geometry("1360x840")
        self.minsize(1180, 760)

        self.prompt_keys = [k for k in DEFAULT_PROMPTS.keys()]
        self.current_key = tk.StringVar(value=self.prompt_keys[0])

        self.current_node_key = self.current_key.get()
        self.text_widget: Optional[tk.Text] = None
        self.token_panel: Optional[TokenPanel] = None

        self._build_ui()
        self._load_current_prompt()

        self.transient(master.root)
        self.grab_set()
        self.focus()

    def destroy(self) -> None:
        try:
            if self.text_widget is not None:
                self.drag_manager.unregister_text_target(self.text_widget)
        except Exception:
            pass
        super().destroy()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=10)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=4)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(1, weight=1)

        top = ttk.Frame(container)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        ttk.Label(top, text="프롬프트 키").pack(side="left")

        combo = ttk.Combobox(
            top,
            values=self.prompt_keys,
            state="readonly",
            textvariable=self.current_key,
            width=36,
        )
        combo.pack(side="left", padx=(8, 0))
        combo.bind("<<ComboboxSelected>>", self._on_prompt_key_changed)

        ttk.Button(top, text="기본값 복원", command=self._restore_default).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="참조 검증", command=self._validate_current_template).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="저장", command=self._save_prompt).pack(side="left", padx=(8, 0))
        ttk.Button(top, text="닫기", command=self.destroy).pack(side="right")

        editor_frame = ttk.Labelframe(container, text="프롬프트 템플릿")
        editor_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        editor_frame.rowconfigure(0, weight=1)
        editor_frame.columnconfigure(0, weight=1)

        self.text_widget = tk.Text(editor_frame, wrap="word", undo=True, font=("Consolas", 10))
        self.text_widget.grid(row=0, column=0, sticky="nsew")

        yscroll = ttk.Scrollbar(editor_frame, orient="vertical", command=self.text_widget.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.text_widget.configure(yscrollcommand=yscroll.set)

        self.drag_manager.register_text_target(self.text_widget)
        self.drag_manager.set_default_insert_callback(self._insert_token)

        right_frame = ttk.Labelframe(container, text="참조 칩 패널")
        right_frame.grid(row=1, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        info = ttk.Label(
            right_frame,
            text=(
                "칩 클릭 또는 드래그로 토큰을 삽입합니다.\n"
                "지원 형식:\n"
                "{{node_key}}, {{node_key.field}}, {{node_key.list[0].field}}"
            ),
            justify="left",
        )
        info.grid(row=0, column=0, sticky="w", padx=8, pady=8)

        self.token_panel = TokenPanel(
            right_frame,
            app=self.app,
            drag_manager=self.drag_manager,
            insert_callback=self._insert_token,
            current_node_key_getter=lambda: self.current_node_key,
        )
        self.token_panel.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

    def _on_prompt_key_changed(self, event=None) -> None:
        self.current_node_key = self.current_key.get()
        self._load_current_prompt()

    def _load_current_prompt(self) -> None:
        if self.text_widget is None:
            return

        key = self.current_key.get()
        self.current_node_key = key
        text = self.app.state["prompts"].get(key, "")

        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", text)

        if self.token_panel is not None:
            self.token_panel.refresh()

    def _insert_token(self, token: str) -> None:
        if self.text_widget is None:
            return
        self.text_widget.insert("insert", token)
        self.text_widget.focus_set()

    def _validate_current_template(self) -> None:
        if self.text_widget is None:
            return

        raw = self.text_widget.get("1.0", "end-1c")
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.current_node_key,
            template_text=raw,
            require_completed=False,
            require_value=False,
        )
        if ok:
            messagebox.showinfo("검증 완료", "프롬프트 참조 형식이 올바릅니다.")
        else:
            messagebox.showerror("검증 실패", msg)

    def _save_prompt(self) -> None:
        if self.text_widget is None:
            return

        key = self.current_key.get()
        new_value = self.text_widget.get("1.0", "end-1c").strip()
        if not new_value:
            messagebox.showwarning("경고", "프롬프트가 비어 있습니다.")
            return

        ok, msg = self.app.validate_template_tokens(
            current_node_key=key,
            template_text=new_value,
            require_completed=False,
            require_value=False,
        )
        if not ok:
            messagebox.showerror("오류", msg)
            return

        self.app.state["prompts"][key] = new_value
        self.app.save()
        self.master_gui.log(f"[완료] 프롬프트 저장: {key}")
        messagebox.showinfo("완료", f"{key} 프롬프트를 저장했습니다.")

    def _restore_default(self) -> None:
        key = self.current_key.get()
        self.app.state["prompts"][key] = DEFAULT_PROMPTS[key]
        self.app.save()
        self._load_current_prompt()
        self.master_gui.log(f"[복원] 기본 프롬프트 복원: {key}")
        messagebox.showinfo("완료", f"{key} 프롬프트를 기본값으로 복원했습니다.")


class NodeDialog(tk.Toplevel):
    def __init__(self, master: "PreviewFlowGUI", app: PreviewFlowApp, node: Node):
        super().__init__(master.root)
        self.master_gui = master
        self.app = app
        self.node = node
        self.drag_manager = DragManager(self)

        self.title(node.name)
        self.geometry("1460x900")
        self.minsize(1260, 780)

        self.content_text: Optional[tk.Text] = None
        self.prompt_text: Optional[tk.Text] = None
        self.response_text: Optional[tk.Text] = None
        self.rendered_text: Optional[tk.Text] = None
        self.token_panel: Optional[TokenPanel] = None

        self._build_ui()
        self._load_initial_data()

        self.transient(master.root)
        self.grab_set()
        self.focus()

    def destroy(self) -> None:
        try:
            for widget in [self.prompt_text, self.response_text, self.rendered_text, self.content_text]:
                if isinstance(widget, tk.Text):
                    self.drag_manager.unregister_text_target(widget)
        except Exception:
            pass
        super().destroy()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=10)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=4)
        container.columnconfigure(1, weight=2)
        container.rowconfigure(0, weight=1)

        if self.node.key == "content_input":
            self._build_content_input_ui(container)
        else:
            self._build_prompt_node_ui(container)

    def _build_content_input_ui(self, parent: ttk.Frame) -> None:
        frame = ttk.Labelframe(parent, text="내용입력")
        frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.content_text = tk.Text(frame, wrap="word", undo=True, font=("Consolas", 11))
        self.content_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        yscroll = ttk.Scrollbar(frame, orient="vertical", command=self.content_text.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.content_text.configure(yscrollcommand=yscroll.set)

        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        ttk.Button(btn_frame, text="저장", command=self._save_content_input).pack(side="left")
        ttk.Button(btn_frame, text="닫기", command=self.destroy).pack(side="right")

    def _build_prompt_node_ui(self, parent: ttk.Frame) -> None:
        left_paned = ttk.Panedwindow(parent, orient="vertical")
        left_paned.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)

        prompt_frame = ttk.Labelframe(left_paned, text="프롬프트 템플릿")
        prompt_frame.rowconfigure(0, weight=1)
        prompt_frame.columnconfigure(0, weight=1)

        self.prompt_text = tk.Text(prompt_frame, wrap="word", undo=True, font=("Consolas", 10))
        self.prompt_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        prompt_scroll = ttk.Scrollbar(prompt_frame, orient="vertical", command=self.prompt_text.yview)
        prompt_scroll.grid(row=0, column=1, sticky="ns")
        self.prompt_text.configure(yscrollcommand=prompt_scroll.set)

        rendered_frame = ttk.Labelframe(left_paned, text="실제 실행용 렌더링 결과")
        rendered_frame.rowconfigure(0, weight=1)
        rendered_frame.columnconfigure(0, weight=1)

        self.rendered_text = tk.Text(rendered_frame, wrap="word", undo=False, font=("Consolas", 10))
        self.rendered_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        rendered_scroll = ttk.Scrollbar(rendered_frame, orient="vertical", command=self.rendered_text.yview)
        rendered_scroll.grid(row=0, column=1, sticky="ns")
        self.rendered_text.configure(yscrollcommand=rendered_scroll.set)

        response_frame = ttk.Labelframe(left_paned, text="외부 LLM 응답 붙여넣기")
        response_frame.rowconfigure(0, weight=1)
        response_frame.columnconfigure(0, weight=1)

        self.response_text = tk.Text(response_frame, wrap="word", undo=True, font=("Consolas", 10))
        self.response_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        response_scroll = ttk.Scrollbar(response_frame, orient="vertical", command=self.response_text.yview)
        response_scroll.grid(row=0, column=1, sticky="ns")
        self.response_text.configure(yscrollcommand=response_scroll.set)

        left_paned.add(prompt_frame, weight=2)
        left_paned.add(rendered_frame, weight=2)
        left_paned.add(response_frame, weight=2)

        self.drag_manager.register_text_target(self.prompt_text)
        self.drag_manager.set_default_insert_callback(self._insert_token_to_prompt)

        right_frame = ttk.Labelframe(parent, text="참조 칩 패널")
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        top_info = ttk.Label(
            right_frame,
            text=(
                "칩 클릭 또는 드래그로 프롬프트에 삽입합니다.\n"
                "전체 노드 / 하위 필드 / 중첩 필드를 지원합니다."
            ),
            justify="left",
        )
        top_info.grid(row=0, column=0, sticky="w", padx=8, pady=8)

        self.token_panel = TokenPanel(
            right_frame,
            app=self.app,
            drag_manager=self.drag_manager,
            insert_callback=self._insert_token_to_prompt,
            current_node_key_getter=lambda: self.node.key,
        )
        self.token_panel.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))

        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        ttk.Button(btn_frame, text="프롬프트 갱신", command=self._reload_prompt_from_saved).pack(side="left")
        ttk.Button(btn_frame, text="토큰 검증", command=self._validate_prompt_tokens).pack(side="left", padx=(6, 0))
        ttk.Button(btn_frame, text="렌더링 미리보기", command=self._render_prompt_preview).pack(side="left", padx=(6, 0))
        ttk.Button(btn_frame, text="렌더링 결과 복사", command=self._copy_rendered_prompt).pack(side="left", padx=(6, 0))
        ttk.Button(btn_frame, text="응답 저장", command=self._save_prompt_response).pack(side="left", padx=(12, 0))

        if self.node.key == "ffmpeg_json":
            ttk.Button(btn_frame, text="출력 파일 저장", command=self._save_ffmpeg_output_file).pack(side="left", padx=(12, 0))

        ttk.Button(btn_frame, text="닫기", command=self.destroy).pack(side="right")

    def _insert_token_to_prompt(self, token: str) -> None:
        if self.prompt_text is None:
            return
        self.prompt_text.insert("insert", token)
        self.prompt_text.focus_set()

    def _load_initial_data(self) -> None:
        data = self.app.state["data"]

        if self.node.key == "content_input" and self.content_text is not None:
            existing = self.app._to_pretty_json_or_text(data.get("content_input", ""))
            self.content_text.delete("1.0", "end")
            self.content_text.insert("1.0", existing)
            return

        if self.prompt_text is not None and self.node.prompt_key:
            prompt = self.app.state["prompts"].get(self.node.prompt_key, "")
            self.prompt_text.delete("1.0", "end")
            self.prompt_text.insert("1.0", prompt)

        if self.response_text is not None and self.node.state_key:
            existing_result = data.get(self.node.state_key, "")
            pretty = self.app._to_pretty_json_or_text(existing_result)
            self.response_text.delete("1.0", "end")
            self.response_text.insert("1.0", pretty)

        if self.token_panel is not None:
            self.token_panel.refresh()

        self._render_prompt_preview()

    def _reload_prompt_from_saved(self) -> None:
        if self.prompt_text is None or not self.node.prompt_key:
            return

        prompt = self.app.state["prompts"].get(self.node.prompt_key, "")
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", prompt)
        self.master_gui.log(f"[프롬프트 갱신] {self.node.name}")
        self._render_prompt_preview()

    def _validate_prompt_tokens(self) -> bool:
        if self.prompt_text is None:
            return False

        raw_prompt = self.prompt_text.get("1.0", "end-1c")
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.node.key,
            template_text=raw_prompt,
            require_completed=True,
            require_value=True,
        )
        if not ok:
            messagebox.showerror("오류", msg)
            return False

        messagebox.showinfo("검증 완료", "참조한 상위 노드 상태와 필드 경로가 모두 정상입니다.")
        return True

    def _render_prompt_preview(self) -> None:
        if self.prompt_text is None or self.rendered_text is None:
            return

        raw_prompt = self.prompt_text.get("1.0", "end-1c")
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.node.key,
            template_text=raw_prompt,
            require_completed=True,
            require_value=True,
        )

        self.rendered_text.delete("1.0", "end")

        if not ok:
            self.rendered_text.insert("1.0", f"[렌더링 불가]\n{msg}")
            return

        try:
            rendered = self.app.render_prompt(self.node, template_override=raw_prompt)
        except Exception as exc:
            self.rendered_text.insert("1.0", f"[렌더링 불가]\n{exc}")
            return

        self.rendered_text.insert("1.0", rendered)

    def _copy_rendered_prompt(self) -> None:
        if self.rendered_text is None:
            return

        raw_prompt = self.prompt_text.get("1.0", "end-1c") if self.prompt_text else ""
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.node.key,
            template_text=raw_prompt,
            require_completed=True,
            require_value=True,
        )
        if not ok:
            messagebox.showerror("오류", msg)
            return

        text = self.rendered_text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.master_gui.log(f"[복사] 렌더링 프롬프트: {self.node.name}")
        messagebox.showinfo("완료", "렌더링 결과를 클립보드에 복사했습니다.")

    def _save_content_input(self) -> None:
        if self.content_text is None:
            return

        content = self.content_text.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showwarning("경고", "내용입력이 비어 있습니다.")
            return

        self.app.state["data"]["content_input"] = content
        self.app.mark_completed("content_input")
        self.app.save()

        self.master_gui.refresh_all()
        self.master_gui.log("[완료] 내용입력 저장")
        messagebox.showinfo("완료", "내용입력을 저장했습니다.")

    def _save_prompt_response(self) -> None:
        if self.prompt_text is None or self.response_text is None or self.node.state_key is None:
            return

        raw_prompt = self.prompt_text.get("1.0", "end-1c")
        ok, msg = self.app.validate_template_tokens(
            current_node_key=self.node.key,
            template_text=raw_prompt,
            require_completed=True,
            require_value=True,
        )
        if not ok:
            messagebox.showerror("오류", msg)
            return

        raw_response = self.response_text.get("1.0", "end-1c").strip()
        if not raw_response:
            messagebox.showwarning("경고", "응답 내용이 비어 있습니다.")
            return

        parsed = self.app._safe_parse_json(raw_response)

        self.app.state["data"][self.node.state_key] = parsed
        self.app.mark_completed(self.node.key)
        self.app.save()

        if self.node.key == "ffmpeg_json":
            try:
                self.app.save_output_file_if_ffmpeg()
            except Exception:
                pass

        if self.token_panel is not None:
            self.token_panel.refresh()

        self.master_gui.refresh_all()
        self.master_gui.log(f"[완료] 노드 결과 저장: {self.node.name}")
        messagebox.showinfo("완료", f"{self.node.name} 결과를 저장했습니다.")

    def _save_ffmpeg_output_file(self) -> None:
        if "ffmpeg_json" not in self.app.state["data"]:
            messagebox.showwarning("안내", "먼저 ffmpeg_json 노드 응답을 저장하세요.")
            return
        try:
            self.app.save_output_file_if_ffmpeg()
            self.master_gui.log(f"[저장] 출력 파일: {self.app.output_path}")
            messagebox.showinfo("완료", f"출력 파일로 저장했습니다.\n{self.app.output_path}")
        except Exception as exc:
            messagebox.showerror("오류", f"출력 파일 저장 실패:\n{exc}")


class PreviewFlowGUI:
    def __init__(self, app: PreviewFlowApp):
        self.app = app
        self.root = tk.Tk()
        self.root.title("HiddenTube Preview Flow GUI v3")
        self.root.geometry("1520x960")
        self.root.minsize(1300, 840)

        self.session_var = tk.StringVar(value=str(self.app.session_path))
        self.output_var = tk.StringVar(value=str(self.app.output_path))

        self.tree: Optional[ttk.Treeview] = None
        self.data_text: Optional[tk.Text] = None
        self.log_text: Optional[tk.Text] = None
        self.summary_label: Optional[ttk.Label] = None

        self._build_ui()
        self.refresh_all()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        path_frame = ttk.Frame(self.root, padding=10)
        path_frame.grid(row=0, column=0, sticky="ew")
        path_frame.columnconfigure(1, weight=1)

        ttk.Label(path_frame, text="세션 파일").grid(row=0, column=0, sticky="w")
        ttk.Entry(path_frame, textvariable=self.session_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(path_frame, text="선택", command=self.select_session_file).grid(row=0, column=2)

        ttk.Label(path_frame, text="출력 파일").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(path_frame, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(path_frame, text="선택", command=self.select_output_file).grid(row=1, column=2, pady=(6, 0))

        top_btn_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        top_btn_frame.grid(row=1, column=0, sticky="ew")

        ttk.Button(top_btn_frame, text="세션 불러오기", command=self.load_session).pack(side="left")
        ttk.Button(top_btn_frame, text="세션 저장", command=self.save_session).pack(side="left", padx=(6, 0))
        ttk.Button(top_btn_frame, text="프롬프트 템플릿 편집", command=self.open_prompt_editor).pack(side="left", padx=(12, 0))
        ttk.Button(top_btn_frame, text="다음 실행 노드 열기", command=self.open_next_runnable_node).pack(side="left", padx=(12, 0))
        ttk.Button(top_btn_frame, text="세션 초기화", command=self.reset_session).pack(side="left", padx=(12, 0))
        ttk.Button(top_btn_frame, text="새로고침", command=self.refresh_all).pack(side="left", padx=(6, 0))

        main_paned = ttk.Panedwindow(self.root, orient="horizontal")
        main_paned.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        left_frame = ttk.Frame(main_paned)
        right_paned = ttk.Panedwindow(main_paned, orient="vertical")

        main_paned.add(left_frame, weight=1)
        main_paned.add(right_paned, weight=2)

        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        self.summary_label = ttk.Label(left_frame, text="", font=("Malgun Gothic", 10, "bold"))
        self.summary_label.grid(row=0, column=0, sticky="w", pady=(0, 8))

        columns = ("status", "name", "runnable")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings", height=18)
        self.tree.grid(row=1, column=0, sticky="nsew")

        self.tree.heading("status", text="상태")
        self.tree.heading("name", text="노드")
        self.tree.heading("runnable", text="실행가능")

        self.tree.column("status", width=80, anchor="center")
        self.tree.column("name", width=420, anchor="w")
        self.tree.column("runnable", width=90, anchor="center")

        tree_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        tree_scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=tree_scroll.set)

        left_btn_frame = ttk.Frame(left_frame)
        left_btn_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        ttk.Button(left_btn_frame, text="선택 노드 열기", command=self.open_selected_node).pack(side="left")
        ttk.Button(left_btn_frame, text="선택 노드 완료해제", command=self.uncomplete_selected_node).pack(side="left", padx=(8, 0))
        ttk.Button(left_btn_frame, text="선택 노드 데이터삭제", command=self.clear_selected_node_data).pack(side="left", padx=(8, 0))

        self.tree.bind("<Double-1>", lambda e: self.open_selected_node())

        data_frame = ttk.Labelframe(right_paned, text="현재 데이터(JSON)")
        self.data_text = tk.Text(data_frame, wrap="none", undo=False, font=("Consolas", 10))
        self.data_text.pack(fill="both", expand=True)

        data_x = ttk.Scrollbar(data_frame, orient="horizontal", command=self.data_text.xview)
        data_y = ttk.Scrollbar(data_frame, orient="vertical", command=self.data_text.yview)
        self.data_text.configure(xscrollcommand=data_x.set, yscrollcommand=data_y.set)
        data_x.pack(fill="x", side="bottom")
        data_y.pack(fill="y", side="right")

        log_frame = ttk.Labelframe(right_paned, text="로그")
        self.log_text = tk.Text(log_frame, wrap="word", height=10, undo=False, font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True)

        right_paned.add(data_frame, weight=3)
        right_paned.add(log_frame, weight=1)

    # ---------- file path ----------
    def select_session_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="세션 파일 선택",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
            initialfile=Path(self.session_var.get()).name,
        )
        if path:
            self.session_var.set(path)
            self.app.session_path = Path(path)
            self.log(f"[경로 변경] 세션 파일: {path}")

    def select_output_file(self) -> None:
        path = filedialog.asksaveasfilename(
            title="출력 파일 선택",
            defaultextension=".json",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
            initialfile=Path(self.output_var.get()).name,
        )
        if path:
            self.output_var.set(path)
            self.app.output_path = Path(path)
            self.log(f"[경로 변경] 출력 파일: {path}")

    # ---------- actions ----------
    def load_session(self) -> None:
        self.app.session_path = Path(self.session_var.get())
        self.app.output_path = Path(self.output_var.get())
        try:
            self.app.load()
            self.refresh_all()
            self.log("[완료] 세션 불러오기")
            messagebox.showinfo("완료", "세션을 불러왔습니다.")
        except Exception as exc:
            self.log(f"[오류] 세션 불러오기 실패: {exc}")
            messagebox.showerror("오류", f"세션 불러오기 실패:\n{exc}")

    def save_session(self) -> None:
        self.app.session_path = Path(self.session_var.get())
        self.app.output_path = Path(self.output_var.get())
        try:
            self.app.save()
            self.refresh_all()
            self.log("[완료] 세션 저장")
            messagebox.showinfo("완료", "세션을 저장했습니다.")
        except Exception as exc:
            self.log(f"[오류] 세션 저장 실패: {exc}")
            messagebox.showerror("오류", f"세션 저장 실패:\n{exc}")

    def reset_session(self) -> None:
        if not messagebox.askyesno("확인", "정말 세션을 초기화할까요?"):
            return
        try:
            self.app.reset_session()
            self.refresh_all()
            self.log("[완료] 세션 초기화")
            messagebox.showinfo("완료", "세션을 초기화했습니다.")
        except Exception as exc:
            self.log(f"[오류] 세션 초기화 실패: {exc}")
            messagebox.showerror("오류", f"세션 초기화 실패:\n{exc}")

    def open_prompt_editor(self) -> None:
        PromptEditorDialog(self, self.app)

    def get_selected_node(self) -> Optional[Node]:
        if self.tree is None:
            return None
        selected = self.tree.selection()
        if not selected:
            return None
        item_id = selected[0]
        tags = self.tree.item(item_id, "tags")
        if not tags:
            return None
        return NODE_MAP.get(tags[0])

    def open_selected_node(self) -> None:
        node = self.get_selected_node()
        if node is None:
            messagebox.showwarning("안내", "노드를 선택하세요.")
            return

        if not self.app.can_run(node) and not self.app.is_completed(node.key):
            deps = ", ".join(node.depends_on) if node.depends_on else "-"
            messagebox.showwarning("안내", f"선행 노드가 완료되지 않았습니다.\n필요: {deps}")
            return

        NodeDialog(self, self.app, node)

    def open_next_runnable_node(self) -> None:
        for node in NODES:
            if self.app.can_run(node) and not self.app.is_completed(node.key):
                NodeDialog(self, self.app, node)
                return
        messagebox.showinfo("안내", "실행 가능한 다음 노드가 없습니다.")

    def uncomplete_selected_node(self) -> None:
        node = self.get_selected_node()
        if node is None:
            messagebox.showwarning("안내", "노드를 선택하세요.")
            return

        self.app.unmark_completed(node.key)
        self.app.save()
        self.refresh_all()
        self.log(f"[완료해제] {node.name}")
        messagebox.showinfo("완료", f"{node.name} 완료 상태를 해제했습니다.")

    def clear_selected_node_data(self) -> None:
        node = self.get_selected_node()
        if node is None:
            messagebox.showwarning("안내", "노드를 선택하세요.")
            return

        if node.state_key and node.state_key in self.app.state["data"]:
            if not messagebox.askyesno("확인", f"{node.name} 데이터를 삭제할까요?"):
                return
            del self.app.state["data"][node.state_key]

        self.app.unmark_completed(node.key)
        self.app.save()
        self.refresh_all()
        self.log(f"[데이터 삭제] {node.name}")
        messagebox.showinfo("완료", f"{node.name} 데이터를 삭제했습니다.")

    # ---------- refresh ----------
    def refresh_all(self) -> None:
        self.refresh_node_tree()
        self.refresh_data_view()
        self.refresh_summary()

    def refresh_summary(self) -> None:
        if self.summary_label is None:
            return
        completed = len(self.app.state.get("completed_nodes", []))
        total = len(NODES)
        self.summary_label.config(
            text=f"진행 상태: {completed}/{total} 완료 | 세션: {self.app.session_path.name}"
        )

    def refresh_node_tree(self) -> None:
        if self.tree is None:
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        for node in NODES:
            done = "✅" if self.app.is_completed(node.key) else "⬜"
            runnable = "예" if self.app.can_run(node) and not self.app.is_completed(node.key) else ""

            self.tree.insert(
                "",
                "end",
                values=(done, node.name, runnable),
                tags=(node.key,),
            )

    def refresh_data_view(self) -> None:
        if self.data_text is None:
            return
        text = json.dumps(self.app.state.get("data", {}), ensure_ascii=False, indent=2)
        self.data_text.delete("1.0", "end")
        self.data_text.insert("1.0", text)

    def log(self, message: str) -> None:
        if self.log_text is None:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")

    def on_close(self) -> None:
        try:
            self.app.session_path = Path(self.session_var.get())
            self.app.output_path = Path(self.output_var.get())
            self.app.save()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_self_test() -> int:
    tmp_session = Path(".tmp_preview_session.json")
    tmp_output = Path(".tmp_preview_output.json")
    app = PreviewFlowApp(tmp_session, tmp_output)

    app.state["data"]["content_input"] = "테스트 입력"
    app.mark_completed("content_input")

    app.state["data"]["script_generation"] = {"title": "제목", "script": "대본"}
    app.mark_completed("script_generation")

    app.state["data"]["scene_breakdown"] = {
        "scenes": [
            {"scene_id": 1, "duration_sec": 2, "visual_desc": "장면1", "narration": "내레이션1"},
            {"scene_id": 2, "duration_sec": 3, "visual_desc": "장면2", "narration": "내레이션2"},
        ]
    }
    app.mark_completed("scene_breakdown")

    tmpl = """
    테스트
    {{content_input}}
    {{script_generation.title}}
    {{scene_breakdown.scenes[0].narration}}
    {{scene_breakdown.scenes}}
    """.strip()

    ok, msg = app.validate_template_tokens(
        current_node_key="image_prompt",
        template_text=tmpl,
        require_completed=True,
        require_value=True,
    )
    assert ok, msg

    rendered = app.render_prompt(NODE_MAP["image_prompt"], template_override=tmpl)
    assert "테스트 입력" in rendered
    assert "제목" in rendered
    assert "내레이션1" in rendered
    assert '"scene_id": 1' in rendered

    # 잘못된 필드 검증
    bad_tmpl = "{{script_generation.summary}}"
    ok, msg = app.validate_template_tokens(
        current_node_key="scene_breakdown",
        template_text=bad_tmpl,
        require_completed=True,
        require_value=True,
    )
    assert not ok
    assert "존재하지 않는 필드입니다" in msg

    # 잘못된 인덱스 검증
    bad_tmpl2 = "{{scene_breakdown.scenes[3].narration}}"
    ok, msg = app.validate_template_tokens(
        current_node_key="image_prompt",
        template_text=bad_tmpl2,
        require_completed=True,
        require_value=True,
    )
    assert not ok
    assert "배열 인덱스가 유효하지 않습니다" in msg

    if tmp_session.exists():
        tmp_session.unlink()
    if tmp_output.exists():
        tmp_output.unlink()

    print("self-test passed")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HiddenTube Preview Flow GUI v3")
    parser.add_argument("--session", default=SESSION_FILE, help="세션 파일 경로")
    parser.add_argument("--output", default=OUTPUT_FILE, help="최종 ffmpeg JSON 출력 경로")
    parser.add_argument("--self-test", action="store_true", help="내장 셀프 테스트 실행")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.self_test:
        return run_self_test()

    try:
        app = PreviewFlowApp(Path(args.session), Path(args.output))
        try:
            app.load()
        except Exception:
            pass

        gui = PreviewFlowGUI(app)
        gui.log("GUI 준비 완료")
        gui.log(f"세션 파일: {app.session_path}")
        gui.log(f"출력 파일: {app.output_path}")
        gui.run()
        return 0
    except Exception as exc:
        print("GUI 실행 중 오류가 발생했습니다.")
        print(exc)
        print(traceback.format_exc())
        return 1


if __name__ == "__main__":
    raise SystemExit(main())