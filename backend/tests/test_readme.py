from pathlib import Path


def test_readme_is_deployment_oriented_and_uses_path_placeholders():
    readme = (Path(__file__).parents[2] / "README.md").read_text(encoding="utf-8")
    assert readme.index("## 启动方式") < readme.index("## 技术选型") < readme.index("## 已完成功能")
    assert "<PROJECT_ROOT>" in readme
    assert "<PYTHON_EXE>" in readme
    assert "D:\\VibeCoding Project Record" not in readme
    assert "token" in readme.lower()
