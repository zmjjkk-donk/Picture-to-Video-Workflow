from pathlib import Path


def test_readme_is_deployment_oriented_and_uses_path_placeholders():
    readme = (Path(__file__).parents[2] / "README.md").read_text(encoding="utf-8")
    assert readme.index("## 启动方式") < readme.index("## 技术选型") < readme.index("## 已完成功能")
    assert "<PROJECT_ROOT>" in readme
    assert "<PYTHON_EXE>" in readme
    assert "D:\\VibeCoding Project Record" not in readme
    assert "token" in readme.lower()


def test_readme_explains_history_preservation_and_task_deletion():
    readme = (Path(__file__).parents[2] / "README.md").read_text(encoding="utf-8")
    assert "## 项目和生成任务的删除规则（第四版）" in readme
    assert "删除项目后" in readme and "历史视频继续保留" in readme
    assert "独立删除标记" in readme
    assert "尚未结束" in readme and "检查点" in readme
