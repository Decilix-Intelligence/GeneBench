# 数据卡：gold 因子面板 **子集**（`gold_subset_v1`）

<!-- 生成件：`$GB/scratch/Y1/y1_mk_card.py`，源 `ops/reports/i_rehearsal_v2/gold_subset.json`。
     子集本身由 `$GB/scratch/Y1/y1_pkg_inventory.py` 算出。**不要手改这一份。** -->

**这份卡回答一个问题：发布包里为什么没有全量 gold，少的那些会不会让你复现不出来。**

## 1. 为什么只发子集

全量 gold 因子面板是 **14.90 GiB**（793 因子 × 3 宇宙 × 2 通道），
超过发布裁定的 5 GB 线。**真正被题用到的只有 41 个因子面板文件，合计 152.0 MiB** —— 少发的那 99% 没有任何一道题读它。

| | 全量 | 本子集 | 比 |
| --- | --- | --- | --- |
| 公开通道 `snapshots/public_v1/gold_factors` | 14.90 GiB | 152.0 MiB（41 件） | 1.00% |
| 私有通道 `snapshots/v1/gold_factors` | 14.91 GiB | 152.0 MiB（41 件） | 1.00% |

## 2. 子集是怎么算出来的（两条来源取并集，宁可多发不可少发）

1. 出集40行+130实例的 gold_args/declared/inputs[].origin
2. s4_eco_pool_v1 选中的 30 条（csi300，读夹具数据卡）

**一条必须先读的限制**：

> 子集能复现夹具内容，不能重新推导池子的选取 —— build_pool() 的合格判定要扫全族每一条（gtja_191 186 条 / worldquant_101 82 条 / qlib_alpha158 158 条）。要重新推导得有全量 gold，走手册 §1.4 (b) 的重建链。

换句话说：**子集能让你跑完题、算出分**；它不能让你重新推导「`s4_eco_pool_v1` 的那 30 条是怎么挑出来的」——那要全量 gold。要审那一步的选取，走手册 §1.4 (b) 从公开源重建一遍（约 4 小时 15 分），或者向发布方要全量包。

## 3. 清单（逐件 sha256）

完整机读清单在 `ops/reports/i_rehearsal_v2/gold_subset.json`（两条通道各 41 行，逐件 `rel` / `bytes` / `sha256`）。

**清单指纹**（把「哪些文件、各自什么 sha」压成一个数，用来一句话比对两份包）：

```
公开通道  6e9696f056986fabacebb3b92717c9a1f44e8c959611979e66b13394054d047d
私有通道  728e86fda980fb4ed399d0f11fbf9a9d75ed019de4538cc202482d10863046a1
```

逐宇宙的因子号：

* **csi300**（37 条）：`gtja_191.001`、`gtja_191.002`、`gtja_191.003`、`gtja_191.012`、`gtja_191.017`、`gtja_191.022`、`gtja_191.043`、`gtja_191.046`、`gtja_191.064`、`gtja_191.085`、`gtja_191.106`、`gtja_191.126`、`gtja_191.147`、`gtja_191.168`、`gtja_191.191`、`qlib_alpha158.BETA10`、`qlib_alpha158.CNTP30`、`qlib_alpha158.IMAX60`、`qlib_alpha158.KSFT2`、`qlib_alpha158.MIN60`、`qlib_alpha158.RESI10`、`qlib_alpha158.RSV5`、`qlib_alpha158.SUMP10`、`qlib_alpha158.VSUMD5`、`qlib_alpha158.WVMA60`、`worldquant_101.001`、`worldquant_101.006`、`worldquant_101.010`、`worldquant_101.019`、`worldquant_101.027`、`worldquant_101.036`、`worldquant_101.045`、`worldquant_101.054`、`worldquant_101.055`、`worldquant_101.071`、`worldquant_101.084`、`worldquant_101.101`
* **csi500**（4 条）：`gtja_191.001`、`gtja_191.002`、`gtja_191.003`、`gtja_191.017`

核一遍（在解开的包里跑，`<root>` 指到 `gold_factors` 那一层）：

```sh
$PY -c "
import json,hashlib,sys,pathlib
d=json.load(open('ops/reports/i_rehearsal_v2/gold_subset.json'))['channels']['public']
root=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else d['root']); bad=[]
for f in d['files']:
    p=root/f['rel']
    h=hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else '(缺件)'
    if h!=f['sha256']: bad.append((f['rel'],h))
print('对上' if not bad else bad)" <root>
```

## 4. 两条通道的同一个因子号**不是同一份数据**

同号文件两条通道的字节数就不一样（公开合计 159,357,698 B / 私有合计 159,350,146 B）—— 复权口径、停牌表示、覆盖面都不同，逐条见 `ops/data_cards/README.md`。**跨通道比数之前先看四条版本轴**（手册 §6.4）。

---

## 换宇宙定义面之后：**公开通道那 41 件从哪里取**（2026-09-12，卡 A，用户裁定 ①）

公开包的 `instruments/` 换成了 baostock 成分接口的重建结果（见
[`ops/reports/public/instruments_switch.md`](../reports/public/instruments_switch.md)）。
gold 面板是**按成分掩膜**落盘的（`reference/factor_exec.py::write_gold` 只留当日在成分内的格），
所以成分一变，公开通道这 41 件的字节就会变。

| | 落点 | 算在哪份 `instruments/` 上 | 拿它做什么 |
| --- | --- | --- | --- |
| **旧** | `$SNAPSHOTS/public_v1/gold_factors/{csi300,csi500}` | `561348660a3175b1…` 那一版（tushare 派生） | 复现**已发布的 18 个公开 run** 与现有 `calibration.json` / crosscheck / ε。**本卡一个字节没动它** |
| **新** | `$SNAPSHOTS/public_v1/gold_factors_r2/{csi300,csi500}` | **`f7dda2899071b07a…`**（baostock 重建） | **打 gold 子集包要从这里取** —— 发出去的分要和发出去的宇宙定义对得上 |

`ops/reports/i_rehearsal_v2/gold_subset.json` 里公开通道那 41 行的 `sha256` **是旧的**，
新的一份在 `$SNAPSHOTS/public_v1/gold_factors_r2/gold_subset_public.json`（逐件 `rel` / `bytes` / `sha256`）。
逐件比对的结论见换面报告 §5。

---

## 发布包里**没有** csi1000：保留在发布方机器上，不随包发（2026-09-13，卡 R2，用户裁定 ③）

| | 值 |
| --- | --- |
| 路径 | `$SNAPSHOTS/public_v1/gold_factors/csi1000` |
| 体量 | **8.3 GiB / 8.9 GB**，792 件 |
| 处置 | **保留在 f01（发布方机器）上，不入任何公开包** |
| 理由 | baostock 0.9.3 **没有中证 1000 成分接口**（只有 `query_hs300_stocks` / `query_zz500_stocks` / `query_sz50_stocks`），这份 csi1000 面板算在**旧的 tushare 派生成分名单**上，而那正是 2026-09-12 换面要去掉的东西 |

**打包脚本确实没收它**，两条独立证据：

1. `ops/release/pack_gold_subset.py` 的源根写死在
   `$GB/snapshots/<public_version>/gold_factors_r2/`（常量 `SUBSET_ROOT_NAME`），
   而 `gold_factors_r2/` 下**只有 `csi300` / `csi500` 两个宇宙**（外加清单
   `gold_subset_public.json` 与 `build_info.json`）—— 源根里根本没有 csi1000 这一支。
   清单从 `gold_subset_public.json` 读、逐件现算 sha256 与它比，对不上当场抛。
2. 两个已发布附件的逐件校验和里 **`csi1000` 命中 0 行**：
   `gold_subset_SHA256SUMS`（46 行）0 行、provider 包的 `SHA256SUMS`（28,656 行）0 行。

**后果**：公开通道只剩 `csi300` / `csi500` / `all` 三个宇宙，
拿公开包**复现不出任何以 `csi1000` 为宇宙的读数**。本子集的 41 件本来就只有
csi300（37 件）与 csi500（4 件），**不受影响**。逐条见
[`ops/reports/known_limits_v1.md`](../reports/known_limits_v1.md)「A（2026-09-12）」一节。

## 随包的**阈值**与本子集**不同源**（2026-09-13，卡 R2）

本子集算在**换面之后**的名单上（`gold_factors_r2/`，根 `f7dda289…`），
而随包的 `calibration.json` / τ / ε 带 / IC 族阈值算在**换面之前**的名单上（根 `56134866…`）。
**拿本子集算分没问题；拿标定在另一份名单上的阈值去判那个分，是跨名单的** ——
贴着阈值的边界样本可能判反。**本轮不重算，重算排 v1.0.17。**
完整说明见 [`DATA_LICENSE`](../../DATA_LICENSE) §6 与 `README.md` §2.1a。
