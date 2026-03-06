from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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


