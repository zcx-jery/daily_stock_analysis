# 娆℃棩寮哄娍鑲＄瓫閫夊瓧娈电骇瀹炵幇鏄犲皠琛?

## 1. 鏂囨。淇℃伅

- 鏂囨。鍚嶇О锛氭鏃ュ己鍔胯偂绛涢€夊瓧娈电骇瀹炵幇鏄犲皠琛?
- 鎵€灞炵郴缁燂細`daily_stock_analysis`
- 閫傜敤鐗堟湰锛歚V1 Standard` / `V1-Aggressive`
- 鏂囨。绫诲瀷锛氬疄鐜板墠鍩虹嚎鏂囨。
- 褰撳墠鐘舵€侊細鑽夋 V1
- 鍏宠仈鏂囨。锛?
  - [娆℃棩寮哄娍鑲＄瓫閫変骇鍝佹柟妗圿(d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-product-plan.md)
  - [娆℃棩寮哄娍鑲＄瓫閫?V1 璇勫垎瑙勫垯](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-scoring-rules.md)
  - [娆℃棩寮哄娍鑲＄瓫閫変簩绾у垎鏁拌鍒橾(d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-secondary-score-rules.md)
  - [娆℃棩寮哄娍鑲＄瓫閫?V1-Aggressive 璇勫垎瑙勫垯](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-v1-aggressive-scoring-rules.md)
  - [娆℃棩寮哄娍鑲＄瓫閫?V1-Aggressive 浜岀骇鍒嗘暟瑙勫垯](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-aggressive-secondary-score-rules.md)
  - [娆℃棩寮哄娍鑲＄瓫閫夎鍒欑敾鍍忓鐓ц〃](d:\AI_Project\_remote_edit\daily_stock_analysis\docs\architecture\momentum-screener-rule-profiles-comparison.md)

## 2. 鏂囨。鐩殑

鏈枃妗ｇ敤浜庢妸浜у搧瑙勫垯杩涗竴姝ユ敹鍙ｅ埌鈥滃疄鐜板墠鍙洿鎺ユ媶浠诲姟鈥濈殑绮掑害銆?

鏈枃妗ｅ洖绛旂殑闂锛?

- 姣忎釜璇勫垎椤逛緷璧栧摢浜涙帴鍙?
- 姣忎釜璇勫垎椤逛緷璧栧摢浜涘師濮嬪瓧娈?
- 姣忎釜璇勫垎椤瑰浣曡绠椾腑闂寸壒寰?
- 缂哄け鍊煎浣曞鐞?
- Standard 鍜?Aggressive 鍝簺鐗瑰緛鍙互鍏辩敤

## 3. 瀹炵幇鍒嗗眰寤鸿

寤鸿鍚庣瀹炵幇鎷嗘垚鍥涘眰锛?

1. 鏁版嵁鎷夊彇灞?
   - 鍙礋璐ｄ粠 Tushare 鎷夋暟鎹?
2. 鐗瑰緛鏋勫缓灞?
   - 鎶婂師濮嬪瓧娈靛姞宸ユ垚缁熶竴鐗瑰緛
3. 璇勫垎瑙勫垯灞?
   - 鎸?`profile=standard/aggressive` 璋冧笉鍚岃瘎鍒嗚鍒?
4. 杈撳嚭缁勮灞?
   - 鐢熸垚椤甸潰/API 杩斿洖瀛楁

杩欐牱鍙互淇濊瘉锛?

- 鏁版嵁鍙媺涓€娆?
- 鐗瑰緛鍙畻涓€娆?
- 涓ゅ瑙勫垯澶嶇敤鍚屼竴鐗瑰緛闆?

## 4. 鎺ュ彛涓庝富鏁版嵁琛?

| 鏁版嵁鍩?| 鎺ュ彛 | 涓昏鐢ㄩ€?|
|---|---|---|
| 鏃ョ嚎琛屾儏 | `daily` | 娑ㄥ箙銆佸紑楂樹綆鏀躲€佹垚浜ら噺銆佹垚浜ら |
| 鑲＄エ鍩虹淇℃伅 | `stock_basic` | 鍚嶇О銆佸競鍦恒€佷笂甯傜姸鎬併€佷笂甯傛棩鏈?|
| 鏃ョ嚎鍩虹鎸囨爣 | `daily_basic` | 鎹㈡墜鐜囥€侀噺姣斻€佹祦閫氬競鍊?|
| 璧勯噾娴佸悜 | `moneyflow` | 涓诲姏鍑€娴佸叆銆佸ぇ鍗?涓崟/灏忓崟缁撴瀯 |
| 榫欒檸姒?| `top_list` | 鏄惁涓婃銆佸噣涔板叆銆佷笂姒滃師鍥?|
| 娑ㄨ穼鍋滀环鏍?| `stk_limit` | 娑ㄥ仠浠枫€佽穼鍋滀环 |
| 琛屼笟鍒嗙被 | `index_classify` | 鐢充竾涓€绾ц涓氬畾涔?|
| 琛屼笟鎴愬垎 | `index_member_all` | 鑲＄エ鍒扮敵涓囦竴绾ц涓氭槧灏?|
| 琛屼笟鏃ョ嚎 | `index_daily` | 鐢充竾涓€绾ц涓氭定璺屽箙銆佹帓鍚?|

## 5. 鍊欓€夋睜纭繃婊ゆ槧灏?

| 瑙勫垯 | 鎵€闇€瀛楁 | 鏉ユ簮鎺ュ彛 | 璇存槑 |
|---|---|---|---|
| 浠婃棩娑ㄥ箙闃堝€?| `pct_chg` | `daily` | `pct_chg >= N` |
| 鎺掗櫎 ST | `name` | `stock_basic` | 鍚嶇О鍖呭惈 `ST/*ST` 杩囨护 |
| 鎺掗櫎鍋滅墝/寮傚父鐘舵€?| `list_status` | `stock_basic` | 浠呬繚鐣?`L` |
| 鎺掗櫎鏂拌偂 | `list_date` | `stock_basic` | 涓婂競鏃堕棿璺濅粖浣庝簬闃堝€艰繃婊?|
| 鏈€浣庢垚浜ら | `amount` | `daily` | 鍊欓€夋睜娴佸姩鎬ч棬妲?|
| 鏈€浣庢崲鎵嬬巼 | `turnover_rate` | `daily_basic` | 鍊欓€夋睜鎹㈡墜闂ㄦ |
| 涓绘澘杩囨护 | `ts_code` 鎴栧競鍦哄瓧娈?| `stock_basic` | 榛樿鍙繚鐣欎富鏉胯偂绁?|

## 6. 鍏叡涓棿鐗瑰緛琛?

浠ヤ笅鐗瑰緛寤鸿缁熶竴鍦ㄧ壒寰佹瀯寤哄眰璁＄畻锛屼袱濂?profile 鍏辩敤銆?

| 鐗瑰緛鍚?| 璁＄畻鍏紡 | 渚濊禆瀛楁 | 鐢ㄩ€?|
|---|---|---|---|
| `close_position` | `(close - low) / (high - low)` | `open/high/low/close` | 鏀剁洏浣嶇疆銆佸熬鐩樺己寮变唬鐞?|
| `limit_proximity` | `close / up_limit` | `close` + `up_limit` | 娑ㄥ仠鎺ヨ繎搴?|
| `body_ratio` | `abs(close - open) / (high - low)` | `open/high/low/close` | K绾垮疄浣撳己搴?|
| `upper_shadow_ratio` | `(high - max(open, close)) / (high - low)` | `open/high/low/close` | 闀夸笂褰?鍐查珮鍥炶惤 |
| `gap_open_ratio` | `(open - prev_close) / prev_close` | `open` + 鍓嶄竴鏃?`close` | 璺崇┖楂樺紑寮哄害 |
| `amplitude_ratio` | `(high - low) / close` | `high/low/close` | 鏃ュ唴鎸箙绌洪棿 |
| `volume_expand_5` | `amount / avg(amount_5)` | 褰撴棩 `amount` + 鍓?5 鏃?`amount` | 鏀鹃噺璐ㄩ噺 / 鐖嗛噺椋庨櫓 |
| `main_inflow_ratio` | `涓诲姏鍑€娴佸叆棰?/ amount` | `moneyflow` + `daily.amount` | 涓诲姏鍑€娴佸叆寮哄害 |
| `prev_20d_high` | 鍓?20 鏃ユ渶楂樹环 | 鍘嗗彶 `daily.high` | 绐佺牬缁撴瀯 |
| `prev_60d_high` | 鍓?60 鏃ユ渶楂樹环 | 鍘嗗彶 `daily.high` | 瓒嬪娍浣嶇疆 |
| `cum_ret_3d` | 杩?3 鏃ョ疮璁℃定骞?| 鍘嗗彶 `daily.pct_chg` | 鍔犻€熷垽鏂?|
| `cum_ret_5d` | 杩?5 鏃ョ疮璁℃定骞?| 鍘嗗彶 `daily.pct_chg` | 杩炵画寮哄娍 / 椋庨櫓 |
| `up_days_5d` | 杩?5 鏃ヤ笂娑ㄥぉ鏁?| 鍘嗗彶 `daily.pct_chg` | 杩炵画寮哄娍 |
| `strong_days_60d` | 杩?60 鏃?`pct_chg >= 7%` 澶╂暟 | 鍘嗗彶 `daily.pct_chg` | 鍘嗗彶鑲℃€?|
| `limit_up_days_60d` | 杩?60 鏃ユ定鍋滃ぉ鏁?| 鍘嗗彶 `daily.close` + `stk_limit.up_limit` | 鍘嗗彶鑲℃€?|

### 6.1 鐗规畩鍊煎鐞?

鑻?`high == low`锛?

- `close_position`
  - 鑻ユ敹娑紝璁?`1.0`
  - 鍚﹀垯璁?`0.5`
- `body_ratio`
  - 鑻?`close > open`锛岃 `1.0`
  - 鍚﹀垯璁?`0.0`
- `upper_shadow_ratio`
  - 璁?`0.0`

## 7. 鏉垮潡鏁版嵁鏄犲皠瑙勫垯

`V1` 涓?`V1-Aggressive` 鐨勬澘鍧楀彛寰勫畬鍏ㄥ叡鐢ㄣ€?

### 7.1 涓绘澘鍧楁槧灏?

| 姝ラ | 閫昏緫 |
|---|---|
| 1 | 鐢?`index_member_all` 灏?`ts_code` 鏄犲皠鍒扮敵涓囦竴绾ц涓?|
| 2 | 鑻ヤ竴鍙偂绁ㄥ瓨鍦ㄥ鏉¤涓氭槧灏勶紝浠呬繚鐣欑敵涓囦竴绾ц涓?|
| 3 | 鐢?`index_daily` 鑾峰彇琛屼笟褰撴棩娑ㄨ穼骞?|
| 4 | 鐢?`daily` 鍦ㄥ悓涓€琛屼笟鍐呯粺璁℃定鍋滄暟銆佸ぇ娑ㄥ鏁般€佷釜鑲℃帓鍚?|

### 7.2 鍥為€€瑙勫垯

濡傛灉鏌愬彧鑲＄エ鏈垚鍔熸槧灏勫埌鐢充竾涓€绾ц涓氾細

- `sector_rank_score` 璁颁腑鎬т綆鍒?
- `sector_breadth_score` 璁颁綆鍒?
- `sector_ladder_score` 璁颁綆鍒?
- `sector_leader_score` 璁颁綆鍒?

寤鸿鍥為€€鍊硷細

| 鐗瑰緛 | 榛樿鍊?|
|---|---:|
| `sector_rank_score_default` | 2 |
| `sector_breadth_score_default` | 1 |
| `sector_ladder_score_default` | 1 |
| `sector_leader_score_default` | 1 |

## 8. Standard 璇勫垎椤规槧灏勮〃

### 8.1 寮哄娍纭璐ㄩ噺

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 浠婃棩娑ㄥ箙寮哄害 | `daily.pct_chg` | 鏃?| 缂哄け鍒欏墧闄ゅ€欓€?|
| 鏀剁洏浣嶇疆 | `daily.open/high/low/close` | `close_position` | 鎸夌壒娈婂€艰鍒欏鐞?|
| 娑ㄥ仠鎺ヨ繎搴?| `daily.close` + `stk_limit.up_limit` | `limit_proximity` | 缂哄け鍒欒椤硅涓€?`2鍒哷 |
| K绾垮疄浣撳己搴?| `daily.open/high/low/close` | `body_ratio` | 鎸夌壒娈婂€艰鍒欏鐞?|

### 8.2 閲忎环缁撴瀯

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 閲忔瘮 | `daily_basic.volume_ratio` | 鏃?| 缂哄け璁颁腑鎬?`3鍒哷 |
| 鎹㈡墜鐜?| `daily_basic.turnover_rate` | 鏃?| 缂哄け璁颁腑鎬?`3鍒哷 |
| 鎴愪氦棰濆垎浣?| `daily.amount` | 鍊欓€夋睜鍐呭垎浣嶆帓鍚?| 缂哄け鍒欏墧闄ゅ€欓€?|
| 鏀鹃噺璐ㄩ噺 | 褰撴棩 `daily.amount` + 鍘嗗彶 `amount` | `volume_expand_5` | 缂哄巻鍙叉椂璁颁腑鎬?`2鍒哷 |

### 8.3 瓒嬪娍浣嶇疆涓庡舰鎬?

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 鍧囩嚎缁撴瀯 | 鍘嗗彶 `daily.close` | `MA5/MA10/MA20` | 鍘嗗彶涓嶈冻鏃惰涓€?`2鍒哷 |
| 绐佺牬缁撴瀯 | 鍘嗗彶 `daily.high` + 褰撴棩 `close/high` | `prev_20d_high`銆乣prev_60d_high` | 鍘嗗彶涓嶈冻鏃惰 `1鍒哷 |
| 杩炵画寮哄娍鐘舵€?| 鍘嗗彶 `daily.pct_chg` | `cum_ret_5d`銆乣up_days_5d` | 鍘嗗彶涓嶈冻鏃惰 `1鍒哷 |

### 8.4 鏉垮潡棰樻潗鍏辨尟

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 鏉垮潡娑ㄥ箙鎺掑悕 | `index_daily` | 琛屼笟娑ㄥ箙鎺掑悕 | 鏄犲皠澶辫触鎸夊洖閫€鍊?|
| 鏉垮潡娑ㄥ仠/澶ф定瀹舵暟 | 琛屼笟鍐?`daily.pct_chg` + `stk_limit` | 鏉垮潡 breadth 缁熻 | 鏄犲皠澶辫触鎸夊洖閫€鍊?|
| 鏉垮潡姊槦瀹屾暣搴?| 琛屼笟鍐?`pct_chg/amount/close_position` | 鏉垮潡姊槦鍒ゅ畾 | 鏄犲皠澶辫触鎸夊洖閫€鍊?|
| 涓偂鏉垮潡鍦颁綅 | 琛屼笟鍐?`pct_chg/amount/close_position` | 琛屼笟鍐呯患鍚堟帓搴?| 鏄犲皠澶辫触鎸夊洖閫€鍊?|

### 8.5 璧勯噾鎵挎帴璐ㄩ噺

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 涓诲姏鍑€娴佸叆缁濆棰?| `moneyflow` 涓诲姏鍑€娴佸叆棰?| 鍊欓€夋睜鍐呮帓鍚?| 缂哄け璁颁腑鎬?`1鍒哷 |
| 涓诲姏鍑€娴佸叆寮哄害 | `moneyflow` + `daily.amount` | `main_inflow_ratio` | 缂哄け璁颁腑鎬?`1鍒哷 |
| 榫欒檸姒滆川閲?| `top_list` | 涓婃/鍑€涔板叆鏍囩 | 鏈笂姒滄寜瑙勫垯璁?`1鍒哷 |
| 浠疯祫涓€鑷存€?| `daily.pct_chg` + `moneyflow` | 鏂瑰悜涓€鑷存€ф爣绛?| 璧勯噾缂哄け璁颁腑鎬?`1鍒哷 |

### 8.6 寮规€т笌鑲℃€?

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 娴侀€氬競鍊煎脊鎬?| `daily_basic.circ_mv` | 鏃?| 缂哄け璁颁腑鎬?`1鍒哷 |
| 鍘嗗彶鑲℃€?| 鍘嗗彶 `daily.pct_chg` + `stk_limit` | `strong_days_60d`銆乣limit_up_days_60d` | 鍘嗗彶涓嶈冻鏃惰 `1鍒哷 |
| 鐭嚎杈ㄨ瘑搴?| 鍘嗗彶寮哄娍璁板綍 + `top_list` | 杩?20 鏃ュ己鍔挎爣璁?| 缂哄け璁?`0鍒哷 鎴栦腑鎬?`1鍒哷锛屽疄鐜板墠瀹氫竴鐗?|

## 9. Aggressive 璇勫垎椤规槧灏勮〃

### 9.1 寮哄娍纭璐ㄩ噺

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 娑ㄥ仠/鍑嗘定鍋滃己搴?| `daily.close` + `stk_limit.up_limit` | `limit_proximity` | 缂哄け璁颁腑鎬?`4鍒哷 |
| 璺崇┖楂樺紑寮哄害 | 褰撴棩 `open` + 鍓嶄竴鏃?`close` | `gap_open_ratio` | 鍓嶆敹缂哄け鍒欒涓€?`3鍒哷 |
| 鏀剁洏鍦颁綅 | `daily.open/high/low/close` | `close_position` | 鎸夌壒娈婂€艰鍒欏鐞?|
| 鍔犻€熺‘璁?| 鍘嗗彶 `pct_chg` + `limit_proximity` | `cum_ret_3d` | 鍘嗗彶涓嶈冻璁?`0鍒哷 |

### 9.2 璧勯噾鎵挎帴璐ㄩ噺

涓?Standard 鍏辩敤瀛楁锛屼絾鏉冮噸鍜屽垎妗ｄ笉鍚屻€?

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 涓诲姏鍑€娴佸叆缁濆棰?| `moneyflow` | 鍊欓€夋睜鍐呮帓鍚?| 缂哄け璁颁腑鎬?`2鍒哷 |
| 涓诲姏鍑€娴佸叆寮哄害 | `moneyflow` + `daily.amount` | `main_inflow_ratio` | 缂哄け璁颁腑鎬?`1鍒哷 |
| 浠疯祫涓€鑷存€?| `daily.pct_chg` + `moneyflow` | 涓€鑷存€ф爣绛?| 璧勯噾缂哄け璁?`1鍒哷 |
| 榫欒檸姒滆川閲?| `top_list` | 涓婃/鍑€涔板叆鏍囩 | 鏈笂姒滄寜瑙勫垯璁?`1鍒哷 |

### 9.3 涔板叆鍙鎬?

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 鏃ュ唴鎸箙绌洪棿 | `daily.high/low/close` | `amplitude_ratio` | 缂哄け鍒欒椤硅 `0鍒哷 |
| 鎴愪氦棰濋粍閲戝尯 | `daily.amount` | 鏃?| 缂哄け鍒欏墧闄ゅ€欓€?|
| 鎹㈡墜鐜囬粍閲戝尯 | `daily_basic.turnover_rate` | 鏃?| 缂哄け璁颁腑鎬?`2鍒哷 |

### 9.4 閲忎环鍙岃建

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 缂╅噺涓€鑷村瀷 | `limit_proximity` + `volume_ratio` | 涓€鑷村瀷鏍囩 | 浠讳竴瀛楁缂哄け璁?`0鍒哷 |
| 鍋ュ悍鎹㈡墜鍨?| `volume_ratio` + `turnover_rate` + `amplitude_ratio` | 鎹㈡墜鍨嬫爣绛?| 浠讳竴瀛楁缂哄け璁颁腑鎬?`3鍒哷 |

### 9.5 鏉垮潡棰樻潗鍏辨尟

涓?Standard 鍏辩敤鏉垮潡鍙ｅ緞鍜屼腑闂寸壒寰侊紝鍙槸鏉冮噸鏇翠綆銆?

### 9.6 瓒嬪娍浣嶇疆涓庡脊鎬?

| 璇勫垎椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 绐佺牬缁撴瀯 | 鍘嗗彶 `daily.high` + 褰撴棩 `close/high` | `prev_20d_high`銆乣prev_60d_high` | 鍘嗗彶涓嶈冻璁?`1鍒哷 |
| 娴侀€氬競鍊煎脊鎬?| `daily_basic.circ_mv` | 鏃?| 缂哄け璁颁腑鎬?`1鍒哷 |
| 鍘嗗彶鑲℃€?| 鍘嗗彶 `daily.pct_chg` + `stk_limit` | `strong_days_60d`銆乣limit_up_days_60d` | 鍘嗗彶涓嶈冻璁?`0鍒哷 |

## 10. 椋庨櫓淇鏄犲皠琛?

### 10.1 Standard

| 椋庨櫓椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 闀夸笂褰?/ 鍐查珮鍥炶惤 | `daily.open/high/low/close` | `upper_shadow_ratio` | 鎸夌壒娈婂€艰鍒?|
| 鐖嗛噺婊炴定 | `daily.amount` + 鍘嗗彶 `amount` + `close_position` | `volume_expand_5` | 缂哄巻鍙茶 `0鍒哷 |
| 灏剧洏璧板急 | `daily.open/high/low/close` | `close_position` | 鎸夌壒娈婂€艰鍒?|
| 楂樹綅杩炵画鍔犻€?| 鍘嗗彶 `pct_chg` | `cum_ret_3d`銆乣cum_ret_5d` | 鍘嗗彶涓嶈冻璁?`0鍒哷 |
| 鏉垮潡閫€娼?| 琛屼笟鏉垮潡鏁版嵁 | 鏉垮潡璺熼殢鏍囩 | 鏄犲皠澶辫触璁?`-1` 鎴?`0`锛屽疄鐜板墠瀹氱 |
| 璧勯噾鑳岀 | `daily.pct_chg` + `moneyflow` | 鑳岀鏍囩 | 璧勯噾缂哄け璁?`0鍒哷 |
| 榫欒檸姒滃亸鍏戠幇 | `top_list` | 鍑€鍗栧嚭鏍囩 | 鏈笂姒滆 `0鍒哷 |

### 10.2 Aggressive

| 椋庨櫓椤?| 鍘熷瀛楁 | 涓棿鐗瑰緛 | 缂哄け鍊煎鐞?|
|---|---|---|---|
| 浠疯祫涓ラ噸鑳岀 | `daily.pct_chg` + `moneyflow` | 鑳岀鏍囩 | 璧勯噾缂哄け璁?`0鍒哷 |
| 鐖嗛噺婊炴定 | `daily.amount` + 鍘嗗彶 `amount` + `close_position` | `volume_expand_5` | 缂哄巻鍙茶 `0鍒哷 |
| 闀夸笂褰?/ 鍐查珮鍥炶惤 | `daily.open/high/low/close` | `upper_shadow_ratio` | 鎸夌壒娈婂€艰鍒?|
| 鏉垮潡閫€娼?| 琛屼笟鏉垮潡鏁版嵁 | 鏉垮潡璺熼殢鏍囩 | 鏄犲皠澶辫触璁?`0鍒哷 |

## 11. 杈撳嚭瀛楁鏄犲皠琛?

| 杈撳嚭瀛楁 | 鏉ユ簮 | 璇存槑 |
|---|---|---|
| `ts_code` | `stock_basic` / `daily` | 鑲＄エ浠ｇ爜 |
| `name` | `stock_basic.name` | 鑲＄エ鍚嶇О |
| `pct_chg` | `daily.pct_chg` | 浠婃棩娑ㄥ箙 |
| `continuation_score` | 浜岀骇鍒嗘暟瑙勫垯 | 涓や釜 profile 鍧囪緭鍑?|
| `extension_score` | 浜岀骇鍒嗘暟瑙勫垯 | 涓や釜 profile 鍧囪緭鍑?|
| `risk_score` | 浜岀骇鍒嗘暟瑙勫垯 | 涓や釜 profile 鍧囪緭鍑?|
| `buyability_score` | Aggressive 浜岀骇鍒嗘暟瑙勫垯 | 浠?Aggressive 杈撳嚭锛孲tandard 鍙繑鍥?`null` |
| `final_score` | 鍩虹鎬诲垎 - 椋庨櫓淇 | 涓昏瘎鍒?|
| `rank_score` | 二级分数排序公式 | 兼容保留的旧排序分 |
| `official_score` | 全候选正式评分公式 | 用户侧唯一官方总分，实时排序不再依赖 `rank_score` |
| `themes` | 鐢充竾涓€绾ц涓?| `V1` 涓绘澘鍧?|
| `leader_level` | 鏉垮潡鍐呮帓搴忔爣绛?| 榫欏ご/鍓嶆帓/涓綅/鍚庢帓 |
| `top_reasons` | 璇勫垎椤归珮鍒嗘爣绛?| 瑙ｉ噴椤?|
| `risk_tags` | 椋庨櫓淇鏍囩 | 椋庨櫓椤?|
| `score_breakdown` | 缁村害寰楀垎鏄庣粏 | 缁村害鎷嗚В |
| `profile` | 璇锋眰鍙傛暟 | `standard` / `aggressive` |

## 12. 璁＄畻椤哄簭寤鸿

寤鸿涓ユ牸鎸変互涓嬮『搴忓疄鐜帮細

1. 鎷夊彇浜ゆ槗鏃ュ拰鑲＄エ姹?
2. 鎵ц鍊欓€夋睜纭繃婊?
3. 鎷夊彇鍊欓€夋睜褰撴棩涓绘暟鎹?
4. 鎷夊彇鍊欓€夋睜鍘嗗彶绐楀彛鏁版嵁
5. 鏋勫缓鍏叡涓棿鐗瑰緛
6. 鏋勫缓琛屼笟鏄犲皠鍜屾澘鍧楃壒寰?
7. 鎸?`profile` 璁＄畻缁村害寰楀垎
8. 璁＄畻椋庨櫓淇
9. 璁＄畻浜岀骇鍒嗘暟
10. 计算 `final_score`、`rank_score` 和 `official_score`，并以 `official_score` 作为官方正式排序依据
11. 鐢熸垚瑙ｉ噴瀛楁鍜岄闄╂爣绛?

## 13. 褰撳墠寰呭畾瀹炵幇椤?

浠ヤ笅鐐瑰凡瓒冲杩涘叆寮€鍙戯紝浣嗗湪鐪熸缂栫爜鍓嶅缓璁啀瀹氫竴娆★細

- `鐭嚎杈ㄨ瘑搴 缂哄け鏃跺埌搴曡 `0` 杩樻槸涓€?`1`
- `鏉垮潡閫€娼甡 鍦ㄦ澘鍧楁槧灏勫け璐ユ椂鏄 `0` 杩樻槸灏忛鎵ｅ垎
- `top_reasons` 鐨勭敓鎴愭槸鎸夐槇鍊兼爣绛捐繕鏄寜 Top 3 楂樺垎椤?
- `leader_level` 鐨勫垏鍒嗘槸鍥哄畾鍚嶆杩樻槸鎸夌櫨鍒嗕綅

## 14. 鍙樻洿璁板綍

### 2026-04-10

- 鍒涘缓瀛楁绾у疄鐜版槧灏勮〃
- 鍥哄寲 Standard 涓?Aggressive 鐨勫叕鍏辩壒寰侀泦
- 鍥哄寲璇勫垎椤逛笌鎺ュ彛銆佸瓧娈点€佺己澶卞€煎鐞嗙殑鏄犲皠鍏崇郴
- 鍥哄寲鎺ㄨ崘璁＄畻椤哄簭
