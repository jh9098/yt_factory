from __future__ import annotations

import argparse
import traceback
from pathlib import Path

from .app_logic import PreviewFlowApp
from .data import NODE_MAP, OUTPUT_FILE, SESSION_FILE
from .gui import PreviewFlowGUI

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
