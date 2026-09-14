# -*- coding: utf-8 -*-
"""卡 B 的判据：⑨ 网关内存与排网格换算 / ⑲ opencode→Qwen 的前置 / ⑳ 代码许可 Apache-2.0。

三件事各自钉的是**能被证伪的东西**，不是措辞：

* ⑨ —— 单元文件里 `MemoryMax` 是 12 G（**不是**「上限被取消」），且两份文档里的换算口径一致。
* ⑲ —— **没有切**：主表 13 条仍是同一个模型，白名单里**没有**一个没人用的域名。
  文档必须把「缺什么、怎么补、补了之后会撞上哪条硬判据」写全。
* ⑳ —— `LICENSE` 里是 Apache-2.0 的**原文逐字**（不是一段像许可的话），
  发布清单的 `code_license_undecided` 因此闭合，而**版权人没有被代填**。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
GATEWAY_UNIT = Path.home() / ".config" / "systemd" / "user" / "genebench-gateway.service"
APACHE_SYS = Path("/usr/share/common-licenses/Apache-2.0")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


# ═══════════════════════════════════════════════ ⑨ 网关内存上限

def test_网关单元的内存上限是12G而不是被取消():
    """N-571：6 G 卡在了**正常工作量**上（一道 S7 真题顶爆 + 4 次 oom-kill），所以抬到 12 G。

    但抬高**不等于**取消：`MemoryMax` 不在了就回到系统级 OOM 去挑进程，
    那正是 N-125 当初划这条线要避免的形态。两件事都要判。
    """
    if not GATEWAY_UNIT.is_file():
        pytest.skip(f"{GATEWAY_UNIT} 不在 —— 这台机上没有部署网关（形态 ① 的机器可能如此）")
    txt = GATEWAY_UNIT.read_text(encoding="utf-8")
    assert re.search(r"^MemoryMax=12G$", txt, re.M), \
        "网关单元的 MemoryMax 不是 12G（用户裁定 ⑨）"
    assert not re.search(r"^MemoryMax=6G$", txt, re.M), "旧的 6G 那行还在"
    assert re.search(r"^MemoryAccounting=yes$", txt, re.M), \
        "MemoryAccounting 没了 —— 没有它 MemoryMax 不生效，而这是**静默**的"
    assert re.search(r"^TimeoutStartSec=600$", txt, re.M), \
        "TimeoutStartSec 被动过：ExecStartPre 的守门要 40–70 s，默认 90 s 是掷硬币（W1）"


def test_排网格的换算写进了两份文档且口径一致():
    """「单 run 峰值 → 并发上限」在 HANDOFF 与手册里各有一节，**数不许分叉**。"""
    handoff = _read(REPO / "ops" / "HANDOFF.md")
    manual = _read(REPO / "docs" / "OPERATOR_MANUAL.md")
    assert "## §19 排网格：从「单 run 峰值」算并发上限" in handoff, "HANDOFF 没有排网格一节"
    assert "## 9. 排网格：一个批里能并发几个 run" in manual, "手册没有排网格一节"
    for name, txt in (("HANDOFF", handoff), ("手册", manual)):
        assert "5.66 M tokens / 87 次调用" in txt, f"{name} 没记 S7 的峰值实测"
        assert "MemoryMax − 常驻" in txt, f"{name} 没写换算式"
        assert "12 G" in txt, f"{name} 没写抬到 12 G 之后的基数"
        assert "gateway_lock" in txt, f"{name} 没说清「批间串行」与「批内并发」是两回事"
        # 外推就要写明是外推 —— 只有 S7 那一行有实测背书
        assert "外推" in txt, f"{name} 把没实测的档位说成了实测"


def test_排网格给出的S7并发上限是不并发():
    """S7 一道就把 2.3 G 常驻推过 6 G 的线；留一倍余量的结论就是**不并发**。"""
    manual = _read(REPO / "docs" / "OPERATOR_MANUAL.md")
    grid = manual.split("## 9. 排网格", 1)[1]
    assert "**1（不并发）**" in grid, "手册的排网格表没写 S7 不并发"
    assert "available` ≥ **20 G**" in grid or "available** ≥ 20 G" in grid or "≥ **20 G**" in grid, \
        "手册没写起批前的内存现查门槛"


# ═══════════════════════════════════════════════ ⑳ 代码许可 Apache-2.0

def test_LICENSE首行的SPDX是Apache_2_0():
    txt = _read(REPO / "LICENSE")
    assert txt.startswith("SPDX-License-Identifier: Apache-2.0\n"), \
        "LICENSE 首行不是 Apache-2.0 的 SPDX 标识（发布清单判的就是这一行）"


def test_LICENSE里是许可原文逐字而不是一段像许可的话():
    """**改过的 Apache-2.0 不再是 Apache-2.0**，而下游合规工具按 SPDX 标识认它、
    不逐字比对 —— 于是「改过」是静默的。这条测试就是那个比对。
    """
    txt = _read(REPO / "LICENSE")
    if APACHE_SYS.is_file():
        canon = APACHE_SYS.read_text(encoding="utf-8")
        assert canon in txt, (
            f"LICENSE 里那份 Apache-2.0 与 {APACHE_SYS} 的原文**不是逐字相同** —— "
            f"少一段或改一个词都会让它不再是 Apache-2.0")
    # 原文在不在都要判的几处骨架（离线机器上 APACHE_SYS 可能不在）
    for need in ("Apache License",
                 "Version 2.0, January 2004",
                 "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION",
                 "3. Grant of Patent License",
                 "9. Accepting Warranty or Additional Liability",
                 "APPENDIX: How to apply the Apache License to your work."):
        assert need in txt, f"LICENSE 里缺 Apache-2.0 原文的这一段：{need!r}"


def test_版权人没有被代填():
    """作者 / 单位 / 地址维持 `<待用户填>`（用户裁定 ⑳ 明确要求）。

    编一个版权人比留一个占位符坏得多：外部用户会照着它做署名与分发决定。
    """
    lic = _read(REPO / "LICENSE")
    cit = _read(REPO / "CITATION.cff")
    # 2026-09-11 用户裁定 ⑩：版权行**由用户自己给定** —— `Copyright 2026 Decilix Intelligence`。
    # 于是这一处不再是占位符。**要拦的事没变**：不许施工方**编**一个版权人；
    # 判据从「必须仍是占位符」换成「必须正是用户给的那一行」。
    assert "Copyright 2026 Decilix Intelligence" in lic, \
        "LICENSE 的版权行不是用户裁定 ⑩ 给的那一行 —— 版权人不许由施工方改写"
    assert "<待用户填" not in lic.split("## 版权行")[0], \
        "版权行之前还有占位符 —— 检查是不是漏填了别处"
    assert re.search(r'^\s*- name: "<待用户填>"', cit, re.M), \
        "CITATION.cff 的 authors 被填了 —— 那是仓库所有者的决定"
    # 2026-09-11（卡 Z）：`repository-code` 那一条**翻过来了** —— 卡 B 写它的时候
    # 地址还没定，所以判「必须仍是占位符」；裁定 ㉑ 给了地址，于是判据变成
    # 「必须是那个真地址」。**这一条的用意没变**：不许施工方替用户编一个值；
    # 变的只是「用户已经说了」这件事。authors 仍然一个字都不许代填（上面那条）。
    # 按**字段行**判，不要按第一次出现的字符串切 —— 头部注释里也写着这个词
    assert re.search(r'^repository-code: "' + re.escape("https://github.com/Decilix-Intelligence/GeneBench.git") + r'"\s*$', cit, re.M), \
        "CITATION.cff 的 repository-code 不是裁定 ㉑ 给的那个地址"


def test_CITATION的license字段是SPDX标识():
    cit = _read(REPO / "CITATION.cff")
    assert re.search(r"^license: Apache-2\.0\s*$", cit, re.M), \
        "CITATION.cff 的 license 不是 `Apache-2.0`（CFF 1.2.0 收的是 SPDX id，不是许可全文）"
    assert "<待用户填：见 LICENSE，代码许可未定>" not in cit, "旧的占位符还在"


def test_发布清单里代码许可那条blocker已闭合而releasable仍是false():
    """闭合的是**这一条**，不是「可以发了」—— 另外三条（两条用户决定 + 一条我们自己的活）还开着。"""
    import importlib
    mr = importlib.import_module("ops.mk_release_manifest")
    assert mr.code_license_id(REPO) == "Apache-2.0"
    assert mr.code_license_decided("Apache-2.0") is True

    bl = {b["id"]: b for b in MANIFEST["blockers"]}
    assert bl["code_license_undecided"]["satisfied"] is True, \
        f"清单里那条还没闭合：{bl['code_license_undecided']['status_now']}"
    assert MANIFEST["license"]["code"] == {"spdx": "Apache-2.0", "file": "LICENSE", "decided": True}
    # **releasable 是推导量，不是这条测试的判据**：它 = 没有缺件 ∧ 五条 blocker 全闭。
    # 这里原来写死 `is False`（当天别的 blocker 还开着）；裁定 ⑨ 闭掉最后一条之后
    # 那句话变成了假。要拦的事没变 —— 闭合的是**代码许可这一条**，
    # 而 `releasable` 必须**与清单自己的推导一致**，不许手改。
    derived = (not MANIFEST["missing"]) and all(b["satisfied"] for b in MANIFEST["blockers"])
    assert MANIFEST["releasable"] is derived, \
        f"releasable 被手改了：清单里缺件 {MANIFEST['missing']}、未闭合 " \
        f"{[b['id'] for b in MANIFEST['blockers'] if not b['satisfied']]}"
    open_ = sorted(b["id"] for b in MANIFEST["blockers"] if not b["satisfied"])
    # 2026-09-11（卡 Z）：原来这里是一张**写死的名单**，它已经被两件事推翻过两次
    # （X1 闭合 public_channel_zero_runs、㉑ 闭合 no_clone_url）。
    # 本条测试要钉的从来不是「还剩哪几条」，而是「**闭合的是代码许可这一条**，
    # 而 releasable 仍然是 false」。所以改成：代码许可不在未闭合名单里、名单非空、
    # 且里面的每一条都是清单自己认得的 id。
    assert "code_license_undecided" not in open_, open_
    assert all(b["id"] in {x["id"] for x in MANIFEST["blockers"]} for b in MANIFEST["blockers"])
    # 这里原来还写着「名单非空」——那是 2026-09-10 的事实，不是判据。
    # 五条今天全闭（裁定 ⑨ 关掉最后一条），名单为空是**正当的**；
    # 要拦的是「名单里混进清单不认得的 id」。
    assert set(open_) <= {b["id"] for b in MANIFEST["blockers"]}, open_


def test_README与手册没有把已定的许可继续说成未定():
    """措辞判两件事：**现状**说的是 Apache-2.0；旧结论**保留但划掉**（读过旧版的人要看得见它去哪了）。"""
    readme = _read(REPO / "README.md")
    manual = _read(REPO / "docs" / "OPERATOR_MANUAL.md")
    assert "**代码许可：[Apache-2.0](LICENSE)**" in readme, "README §6 没写现在的许可"
    assert "~~**代码许可未定**~~" in readme, "README §5 那条没有按「划掉 + 已闭合」的写法保留"
    assert "~~**代码许可未定。**~~" in manual, "手册 §0.1 第 4 条没有按「划掉 + 已闭合」的写法保留"
    # §0.1 的条数判的是 blockers 的**总**条数（5），不是未闭合数 —— 别把它改成 3
    head = manual.split("### 0.2")[0]
    #: 标题里那句「哪几条已闭合」跟着 `RELEASE_MANIFEST.blockers` 走
    #: （2026-09-11 卡 X1 之后是第 2–5 条；红队 V2.rt finding 4 改的就是这里）。
    #: 逐条对齐由 `ops/test_V2rt.py::test_manual_front_page_does_not_contradict_the_blockers`
    #: 钉住（它比的是**条数**，不是措辞）；这里只守「总条数仍是五件」这半句。
    # 2026-09-12：五条**全部**闭合（裁定 ⑨ 关掉最后一条），所以标题里那句
    # 「哪几条已闭合」变成了「五条全部已闭合」。守的仍是同一件事 ——
    # §0.1 摊开的是 blockers 的**总**条数（五件），别把它改成未闭合数。
    assert "五件" in head and "五条全部已闭合" in head


def test_README里未闭合的条数与清单一致():
    """README §5 的那个中文数字是**推导量**，blocker 增减时必须跟着改 —— 少写一条就是粉饰。"""
    n = len([b for b in MANIFEST["blockers"] if not b["satisfied"]])
    cn = {0: "零", 1: "一", 2: "两", 3: "三", 4: "四", 5: "五"}[n]
    body = _read(REPO / "README.md").split("## 5. 发布状态", 1)[1].split("\n## ", 1)[0]
    assert f"未闭合的{cn}条" in body, f"清单里有 {n} 条未闭合，README §5 没写「未闭合的{cn}条」"


# ═══════════════════════════════════════════════ ⑲ opencode / Qwen

@pytest.fixture(scope="module")
def REG():
    from runner import registry as r
    return r


def test_主表仍然是一个模型乘多种harness(REG):
    """`assert_registry_sane` 的「所有已启用配置同一模型」是 **v1.0 的实验设计**，不是卫生检查。

    本卡**没有**放宽它，也没有往主表里塞一条别的模型 —— 这条测试就是那个承诺。
    """
    REG.assert_registry_sane()
    models = {c.model for c in REG.CONFIGS}
    assert models == {"deepseek-chat"}, f"主表里出现了别的模型：{sorted(models)}"
    assert len(REG.CONFIGS) >= 13, f"主表配置少了：{len(REG.CONFIGS)}"


def test_opencode那条配置没有被本卡动过(REG):
    """裁定是切 Qwen，但前置缺 key。**把主表里正在用的那条改掉**不是「准备好」，是拿走一条配置。"""
    import yaml
    cfg = yaml.safe_load((REPO / "harnesses" / "opencode" / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["model"] == "deepseek-chat", "opencode 的模型被改了，但 Qwen 的前置并没有齐"
    assert cfg["enabled"] is True, "opencode 被关掉了 —— 那是从主表里拿走一条正在用的配置"
    assert cfg["api_key_env"] == "DEEPSEEK_API_KEY"


def test_白名单里没有一个没人用的域名(REG):
    """出向白名单的判据是**键集相等**：有 enabled 配置需要才进，没人用的域名是纯粹的敞口。

    dashscope 今天**不该**在里面 —— Qwen 那条还没有（也不会以 enabled 的形态）落地。
    """
    import sys
    sys.path.insert(0, str(REPO / "runner" / "c41"))
    from egress_proxy import MODEL_API_ALLOW      # noqa: E402
    assert set(MODEL_API_ALLOW) == set(REG.collect_egress_hosts()), \
        "白名单与 registry 漂了（键集必须相等，不是包含）"
    assert "dashscope.aliyuncs.com" not in MODEL_API_ALLOW, \
        "dashscope 进白名单了，但没有任何 enabled 配置需要它"


def test_opencode文档把Qwen的前置与判据写全了():
    """『前置未齐』不是一句「待办」就完事 —— 缺什么、怎么查、补了之后撞哪条硬判据，三件都要在。"""
    doc = _read(REPO / "harnesses" / "opencode" / "README.md")
    assert "## §9 换到 Qwen（用户裁定 ⑲" in doc, "opencode README 没有 Qwen 那一节"
    for need, why in (
        ("DASHSCOPE_API_KEY", "key 变量名"),
        ("https://dashscope.aliyuncs.com/compatible-mode/v1", "OpenAI 兼容端点"),
        ("dashscope.aliyuncs.com", "要进白名单的域名"),
        ("assert_registry_sane", "会撞上的那条硬判据"),
        ("PENDING_CONFIGS", "不放宽断言的做法"),
        ("enabled: false", "同上"),
        ("0600", "key 的落点与权限"),
        ("401", "连通性实测结论"),
    ):
        assert need in doc, f"opencode README §9 没写{why}（缺 {need!r}）"
    assert "**没有切**" in doc or "前置未齐" in doc, "没说清今天到底切没切"


def test_QwenCode不做且没有地方还把它当计划():
    """裁定 ⑲：`@qwen-code/qwen-code` 不接。手册与 harnesses/README 里不许再有「计划中」的措辞。"""
    hr = _read(REPO / "harnesses" / "README.md")
    manual = _read(REPO / "docs" / "OPERATOR_MANUAL.md")
    assert "Qwen Code CLI）不做" in hr or "不做**（裁定 ⑲）" in hr, \
        "harnesses/README 没有把「Qwen Code 不做」写明"
    assert "qwen-code" not in manual, "手册里还提着 Qwen Code"
    # harnesses/README 里出现 qwen-code 只允许是「不做」的那句
    for m in re.finditer(r"qwen-code", hr):
        seg = hr[max(0, m.start() - 200): m.start() + 200]
        assert "不做" in seg, f"harnesses/README 里有一处 qwen-code 不是在说「不做」：{seg[:120]!r}"


def test_harnesses的README说清了为什么只有一个模型():
    hr = _read(REPO / "harnesses" / "README.md")
    assert "## 7. 模型只有 DeepSeek 一条现网链路" in hr
    assert "一个模型 × 多种 harness" in hr, "没写这条约束的**用意**，只写了约束"
    assert "M7" in hr, "没写「放宽要过 M7」"
    assert "DASHSCOPE_API_KEY" in hr, "没写 Qwen 缺的到底是什么"


def test_本卡没有把真key写进任何地方():
    """红线 3：凭据不进仓库、不进日志。本卡碰过的文件逐个扫一遍（口径与 ops/test_env.py 同源）。"""
    import importlib
    te = importlib.import_module("ops.test_env")
    mine = ["LICENSE", "CITATION.cff", "README.md", "docs/OPERATOR_MANUAL.md",
            "ops/HANDOFF.md", "harnesses/README.md", "harnesses/opencode/README.md",
            "ops/test_B.py", "ops/tickets_inbox/B.md"]
    pub = te._public_strings()
    bad = []
    for rel in mine:
        p = REPO / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat, why in te._KEY_SHAPES:
            for m in re.finditer(pat, text):
                if any(s in m.group(0) for s in pub):
                    continue          # 边车占位 key：具名例外，它没有任何权限
                bad.append(f"{rel}: {why}")
    assert not bad, bad
