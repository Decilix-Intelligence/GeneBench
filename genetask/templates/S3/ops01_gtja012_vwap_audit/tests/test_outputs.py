# 容器内自检：只查结构，不查对错（对错由数据面 scorer 结算）。
import json, os, pathlib

def test_artifact_exists_and_is_structural():
    p = pathlib.Path("/task/artifact.json")
    assert p.exists(), "没有产出 /task/artifact.json"
    a = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(a.get("schema_version"), str), "schema_version 必须是字符串"
    assert a.get("stage") == os.environ.get("GENEBENCH_STAGE", a.get("stage"))
    assert a.get("task_id") == os.environ.get("GENEBENCH_TASK_ID", a.get("task_id"))
