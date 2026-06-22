# veda_ped_analyzer 使い方マニュアル

Repository: https://github.com/fatalfailure/veda_ped_analyzer
## 1. このプログラムの目的

`veda_ped_analyzer.py` は、VEDA の PED（Potential Energy Distribution）解析結果を使って、**任意に選択した内部座標がどの振動モードに含まれているか**を追跡するための汎用 GUI ツールです。

金属錯体における金属–配位子伸縮の探索にも使えますが、このソフトは金属錯体専用ではありません。芳香環 C-C 伸縮、C=O 伸縮、特定結合の変角、ねじれ座標など、ユーザーが指定した任意の内部座標群を target として追跡できます。

従来型の PED 表では、各振動モードについて寄与率上位の内部座標だけを確認します。一方、このプログラムでは、注目した内部座標を target として指定し、その内部座標がどの mode に何 % 含まれているかを縦方向に追跡できます。

---

## 2. 必要な入力ファイル

解析には、基本的に以下のファイルを使用します。

| ファイル | 必須 | 内容 |
|---|---:|---|
| `.ved` | 必須 | VEDA の PED 行列を含むファイル |
| `.dd2` | 必須 | VEDA の内部座標定義ファイル |
| `.fmu` | 推奨 | atom index と元素記号の対応に使用 |
| `.out` または `.log` | 必須 | ORCA または Gaussian の振動解析 output |

`.fmu` がない場合、QC output の座標ブロックから元素記号の対応を推定します。ただし、金属–配位子結合を正確に抽出したい場合は `.fmu` を指定することを推奨します。

---

## 3. 起動方法

コマンドラインまたは Python 実行環境から、以下のように実行します。

```bash
python veda_ped_analyzer.py
```

実行すると GUI が開きます。

---

## 4. 画面構成

GUI は以下のタブで構成されています。

| タブ | 役割 |
|---|---|
| Files / Precheck | 入力ファイルの選択と読み込み確認 |
| Coordinate Browser | DD2 内部座標の閲覧・フィルタ・target 追加 |
| Target Definition | 追跡したい内部座標セットの定義 |
| Run Analysis | 出力内容・しきい値・周波数範囲の指定と解析実行 |
| Results Preview | 解析結果の簡易表示 |
| User Guide | GUI 内ヘルプ |

---

## 5. 基本的な解析手順

### Step 1. ファイルを選択する

`Files / Precheck` タブで、以下を選択します。

1. `Select .ved`
2. `Select .dd2`
3. `Select .fmu`
4. `Select QC output`
5. 必要に応じて `Select output folder`

`.ved` を選択すると、同じフォルダに同名の `.dd2`, `.fmu`, `.out`, `.log` がある場合、自動で補完されます。

出力フォルダを指定しない場合、基本的には `.ved` ファイルと同じフォルダに CSV が出力されます。

---

### Step 2. Precheck を実行する

`Files / Precheck` タブで、

```text
Load / Precheck
```

を押します。

ここで以下が確認されます。

- VEDA の PED matrix が読めるか
- DD2 の内部座標が読めるか
- FMU または QC output から atom map が作れるか
- ORCA または Gaussian の振動数・IR intensity が読めるか
- VEDA mode と QC mode が振動数ベースで対応付けできるか
- PED block と coordinate code が検出されるか

Precheck summary に、mode 数、PED block 数、DD2 座標数、QC engine、mode mapping の結果などが表示されます。

#### 確認すべき項目

特に以下を確認してください。

```text
Mode mapping matched
Max |Δfreq|
Detected coordinate sets
Atom map
```

`Max |Δfreq|` が大きい場合、VEDA と QC output の対応がずれている可能性があります。

---

### Step 3. 内部座標を探す

`Coordinate Browser` タブでは、DD2 から読み込まれた内部座標が一覧表示されます。

主な列は以下です。

| 列 | 意味 |
|---|---|
| coord_id | DD2 内部座標 ID |
| code | 座標解釈コード。例: `s`, `k`, `v` |
| group | 座標種別。例: `STRE`, `BEND`, `TORS` |
| atoms | atom index の並び |
| atom_label | 元素記号付きの atom label |
| label | 簡易ラベル。例: `str(Co1-N14)` |
| raw_label | VEDA/DD2 側の元ラベル |

#### フィルタ機能

以下の条件で絞り込めます。

| フィルタ | 例 | 用途 |
|---|---|---|
| Coordinate set | `s - standard` | 標準の内部座標解釈だけを見る |
| Group | `STRE - Stretching` | 伸縮座標だけを見る |
| Contains atom index | `1` | 金属原子 index を含む座標だけを見る |
| Contains element | `Co` | Co を含む座標だけを見る |
| Label contains | `Co-N` | ラベル文字列で絞る |


#### Coordinate set の意味

Coordinate set は VEDA/DD2 の内部座標解釈コードを分かりやすく表示したものです。`Code` は座標そのものではなく、座標解釈の種類を表します。

| 表示 | 意味 |
|---|---|
| `s - standard` | 標準の内部座標解釈 |
| `k - alternative` | 代替内部座標解釈 |
| `v - alternative2` | 2つ目の代替内部座標解釈 |
| `(any)` | すべての座標解釈を表示 |

Coordinate Browser は初期状態で `s - standard` と `STRE - Stretching` を選択します。

金属–配位子伸縮を探す場合は、まず以下のように絞ると便利です。

```text
Group = STRE
Contains atom index = 金属原子の atom index
```

---

### Step 4. Target 座標を指定する

Target とは、追跡したい内部座標の集合です。


`target_set_name` は、出力 CSV に記録される target 座標群のラベルです。これは計算モードではありません。デフォルトは `target_coordinates` で、必要に応じて `ring_CC_stretches`, `carbonyl_modes`, `Co_N_stretches` のように変更できます。


例えば、Co 錯体で Co–N 伸縮を追跡したい場合、Co–N に対応する複数の `coord_id` を target に登録します。

#### 方法 A: Coordinate Browser から手動追加

1. `Coordinate Browser` で目的の内部座標を選択します。
2. `Add selected to target` を押します。
3. `Target Definition` タブの `Target coord_id list` に ID が追加されます。

#### 方法 B: 金属–配位子伸縮を自動検出

`Target Definition` タブで以下を指定します。

| 項目 | 例 | 意味 |
|---|---|---|
| Target set name | `target_coordinates` など | 出力 CSV に記録されるユーザー定義ラベル |
| Metal atom index/indices | `1` | 金属原子の atom index |
| Ligand atom indices | `14 15 16 17` | 配位原子を index で限定する場合 |
| Ligand elements | `N O S Cl` | 配位原子を元素で限定する場合 |

その後、

```text
Replace by auto-detect
```

または

```text
Auto-detect M-L stretches
```

を押します。

自動検出では、主に以下の条件を満たす DD2 座標が target 候補になります。

```text
coord_group が STRE
原子数が 2
片方が金属原子
もう片方が配位原子
```

#### 注意

金属元素の自動判定も可能ですが、錯体解析では **Metal atom index/indices を明示することを推奨**します。

---

### Step 5. 解析条件を設定する

`Run Analysis` タブで、出力内容としきい値を設定します。

#### Output options

| オプション | 推奨 | 内容 |
|---|---:|---|
| Standard top-N PED table | ON | 従来型の mode 中心 PED 表 |
| Long PED table | ON | 全 PED contributor を縦長形式で出力 |
| Target hits | ON | target 座標が含まれる mode を一覧出力 |
| Target summary by mode | ON | mode ごとに target PED 合計を出力 |
| Target summary by coordinate | ON | 内部座標ごとに出現 mode を集計 |
| Target matrix | ON | mode × target coord_id の行列を出力 |
| Include target modes below total threshold | 必要に応じて | target 合計 PED がしきい値未満の mode も残す |

通常はすべて ON で問題ありません。

#### Thresholds and frequency range

| 項目 | 例 | 意味 |
|---|---:|---|
| Top N in standard table | `6` または `10` | 従来型表に出す上位 PED 数 |
| Standard table min PED (%) | `0.1` | 従来型表で表示する最小 PED |
| Long table min PED (%) | `0.1` | long table に保存する最小 PED |
| Target hit min PED (%) | `0.1` | target hit として扱う最小 PED |
| Target total min PED per mode (%) | `1.0` | target summary by mode に残す最小合計 PED |
| Freq min (cm^-1) | `200` | 解析対象の下限周波数 |
| Freq max (cm^-1) | `800` | 解析対象の上限周波数 |

金属–配位子伸縮が指紋領域に分裂している場合、例えば以下のように設定します。

```text
Freq min = 200
Freq max = 800
Target hit min PED = 0.1
Target total min PED per mode = 1.0
```

---

### Step 6. 解析を実行する

`Run Analysis` タブで、

```text
RUN TARGET ANALYSIS
```

を押します。

解析が完了すると、保存された CSV ファイル名が表示されます。結果の一部は `Results Preview` タブにも表示されます。

---

## 6. 出力ファイルの説明

出力ファイル名は、入力 `.ved` のファイル名を基準に作られます。

例えば入力が

```text
sample.ved
```

の場合、以下のような CSV が出力されます。

---

### 6.1 Standard PED table

```text
sample_PED_table_standard.csv
sample_PED_table_alternative_k.csv
sample_PED_table_alternative_v.csv
```

従来型の PED 表です。各 mode について、寄与の大きい内部座標を上位 N 個まで出力します。

主な列：

| 列 | 意味 |
|---|---|
| mode_veda | VEDA 側 mode 番号 |
| mode_qc | ORCA/Gaussian 側 mode 番号 |
| freq_veda | VEDA 側振動数 |
| freq_qc | QC output 側振動数 |
| IR_intensity | IR intensity |
| PED1_label, PED1_val | 最大寄与の内部座標と値 |
| PED2_label, PED2_val | 2番目の寄与 |
| total_target_PED | target 座標群の合計 PED |
| top_target_terms | target 座標の主な内訳 |

---

### 6.2 Long PED table

```text
sample_PED_terms_long_standard.csv
```

全 mode × 全内部座標の PED contributor を縦長形式で保存します。

主な列：

| 列 | 意味 |
|---|---|
| mode_veda | VEDA 側 mode |
| mode_qc | QC 側 mode |
| freq_qc | QC 側振動数 |
| PED_rank | その mode 内での PED 順位 |
| PED_value | PED 寄与率 |
| coord_id | 内部座標 ID |
| coord_code | 座標コード |
| coord_group | STRE/BEND/TORS など |
| atom_label | 元素記号付き atom label |
| label | 内部座標ラベル |
| is_target | target 座標かどうか |

この表は、rank 7 以下に埋もれた金属–配位子伸縮を確認するために重要です。

---

### 6.3 Target hits

```text
sample_target_hits_standard.csv
```

指定した target 内部座標が、どの mode にどの程度含まれているかを一覧します。

主な列：

| 列 | 意味 |
|---|---|
| target_set_name | 選択した内部座標群に付けたユーザー定義ラベル。計算モードではない |
| coord_id | target 内部座標 ID |
| label | 内部座標ラベル |
| mode_qc | QC 側 mode |
| freq_qc | QC 側振動数 |
| PED_value | その target 座標の PED 値 |
| PED_rank | その mode 内での順位 |
| IR_intensity | IR intensity |

特定の Co–N 伸縮がどの振動モードに出ているかを見るには、この表を使います。

---

### 6.4 Target summary by mode

```text
sample_target_summary_by_mode_standard.csv
```

今回の解析で最も重要な出力です。

各 mode について、target 座標群の PED を合計します。

主な列：

| 列 | 意味 |
|---|---|
| mode_qc | QC 側 mode |
| freq_qc | QC 側振動数 |
| IR_intensity | IR intensity |
| total_target_PED | target 座標群の合計 PED |
| max_target_PED | target 座標の中で最大の PED |
| n_target_coords_detected | その mode に含まれた target 座標数 |
| best_target_rank | target 座標の中で最も高い順位 |
| top_target_terms | target 寄与の主な内訳 |

金属–配位子伸縮が複数の内部座標に分裂している場合、個々の寄与が小さくても `total_target_PED` が大きくなります。

まずこのファイルを開き、`total_target_PED` が大きい mode を確認することを推奨します。

---

### 6.5 Target summary by coordinate

```text
sample_target_summary_by_coord_standard.csv
```

target 内部座標ごとに、どの mode に強く現れるかを集計します。

主な列：

| 列 | 意味 |
|---|---|
| coord_id | 内部座標 ID |
| label | 内部座標ラベル |
| max_PED | 最大 PED 値 |
| mode_qc_at_max | 最大 PED を示す QC mode |
| freq_qc_at_max | 最大 PED を示す振動数 |
| sum_PED_in_range | 指定周波数範囲内での PED 合計 |
| weighted_mean_freq | PED 重み付き平均周波数 |
| n_modes_detected | 検出された mode 数 |
| top_modes | 主な出現 mode |

各配位結合がどの周波数領域に分散しているかを見るのに便利です。

---

### 6.6 Target matrix

```text
sample_target_matrix_standard.csv
```

行が mode、列が target coord_id の行列形式です。

Excel や pandas でヒートマップを作る場合に便利です。

---

### 6.7 Coordinates lookup

```text
sample_coordinates_lookup.csv
```

DD2 内部座標の一覧表です。

主な列：

| 列 | 意味 |
|---|---|
| coord_id | 内部座標 ID |
| coord_code | 座標コード |
| coord_group | 座標種別 |
| atoms | atom index |
| atom_label | 元素記号付き atom label |
| label | 簡易ラベル |
| source_line | DD2 の元行 |

解析前に coord_id を確認したい場合にも使えます。

---

## 7. Results Preview の見方

`Results Preview` タブには、主に以下の3つの表が表示されます。

| 表 | 用途 |
|---|---|
| Summary by mode | target PED 合計が大きい mode を探す |
| Target hits | target 内部座標ごとの出現 mode を見る |
| Summary by coordinate | 各 target 座標がどこに分散しているかを見る |

最初に見るべきなのは **Summary by mode** です。

以下の列を確認してください。

```text
total_target_PED
freq_qc
IR_intensity
top_target_terms
```

`total_target_PED` が大きく、かつ `IR_intensity` も大きい mode は、実験 IR/Raman スペクトルの帰属候補として優先的に確認する価値があります。

---

## 8. 金属–配位子伸縮を探す推奨ワークフロー

### 例: Co–N 伸縮を 200–800 cm^-1 で探す

1. `Files / Precheck` でファイルを選ぶ。
2. `Load / Precheck` を押す。
3. `Coordinate Browser` で以下を指定する。

```text
Group = STRE
Contains atom index = Co の atom index
```

4. Co–N に対応する内部座標を選択し、`Add selected to target` を押す。
5. `Target Definition` で target 名を設定する。

```text
Target set name = Co_N_stretches
```

6. `Run Analysis` で以下を設定する。

```text
Freq min = 200
Freq max = 800
Target hit min PED = 0.1
Target total min PED per mode = 1.0
```

7. `RUN TARGET ANALYSIS` を押す。
8. `Results Preview` の `Summary by mode` を見る。
9. `total_target_PED` が大きい mode を候補として確認する。
10. 詳細は `Target hits` または `PED_terms_long` で確認する。

---

## 9. 設定 JSON とログ

このプログラムは、前回使用した設定を JSON ファイルに保存します。

設定ファイル名は通常、以下です。

```text
veda_ped_analyzer.json
```

実行ファイルの場所に書き込めない場合は、ホームディレクトリに保存されます。

```text
~/veda_ped_analyzer.json
```

保存される主な項目は以下です。

- 前回選択した `.ved`, `.dd2`, `.fmu`, `.out/.log`
- 出力フォルダ
- target 名
- 金属 atom index
- 配位原子 atom index
- 配位元素
- target coord_id list
- Top N
- PED しきい値
- 周波数範囲

ログファイルは通常、以下に保存されます。

```text
veda_ped_analyzer.log
```

または、ホームディレクトリ側の

```text
~/veda_ped_analyzer.log
```

です。

エラーや警告が出た場合は、ログファイルを確認してください。

---

## 10. よくある問題と対処

### Q1. Coordinate Browser が空です

以下を確認してください。

- `.dd2` が正しく選択されているか
- `Load / Precheck` を実行したか
- DD2 ファイル形式が想定と大きく違っていないか

---

### Q2. 元素記号が表示されません

`.fmu` が読み込めていない可能性があります。

対処：

- `.fmu` を明示的に選択する
- QC output に座標情報が含まれているか確認する
- Precheck summary の atom map 関連表示を確認する

---

### Q3. Target が自動検出されません

以下を確認してください。

- `Metal atom index/indices` が正しいか
- `Ligand elements` が正しいか
- DD2 で対象座標の `group` が `STRE` として登録されているか
- atom index が FMU/QC output の原子番号と一致しているか

金属錯体では、元素だけでなく **metal atom index を明示する**方が安全です。

---

### Q4. Target summary by mode が空です

以下を確認してください。

- target coord_id list が空ではないか
- `Target total min PED per mode (%)` が高すぎないか
- `Freq min` / `Freq max` が狭すぎないか
- `Include target modes below total threshold` を ON にして再実行する

---

### Q5. VEDA mode と QC mode の対応が怪しいです

Precheck summary の `Max |Δfreq|` を確認してください。

差が大きい場合、以下の可能性があります。

- VEDA に使った振動解析結果と QC output が一致していない
- imaginary mode や低振動 mode の扱いが異なる
- ORCA/Gaussian output の別計算ファイルを選んでいる
- VEDA 側と QC 側で mode 数が異なる

---

## 11. 解析結果の読み方のコツ

金属–配位子伸縮が複数 mode に分裂している場合、1つの内部座標だけを見ると寄与が小さく見えることがあります。

そのため、以下の順で確認することを推奨します。

1. `target_summary_by_mode` で `total_target_PED` が大きい mode を探す。
2. `top_target_terms` で、どの M–L 結合が効いているかを見る。
3. `target_hits` で個別の `coord_id` ごとの分布を見る。
4. `PED_terms_long` で、target 以外の成分も含めて mode の全体像を見る。
5. 実験スペクトルと比較する場合は、`freq_qc` と `IR_intensity` も併せて見る。

---

## 12. 推奨設定

金属–配位子伸縮の探索では、まず以下の設定から始めることを推奨します。

```text
Top N in standard table = 6 または 10
Standard table min PED (%) = 0.1
Long table min PED (%) = 0.1
Target hit min PED (%) = 0.1
Target total min PED per mode (%) = 1.0
Freq min = 200
Freq max = 800
```

結果が多すぎる場合は、次のように調整します。

```text
Target hit min PED (%) = 0.5
Target total min PED per mode (%) = 2.0
```

結果が少なすぎる場合は、次のように調整します。

```text
Target total min PED per mode (%) = 0.3
Include target modes below total threshold = ON
```

---

## 13. 用語メモ

| 用語 | 意味 |
|---|---|
| PED | Potential Energy Distribution。振動 mode に対する内部座標の寄与率 |
| mode_veda | VEDA 側の振動 mode 番号 |
| mode_qc | ORCA/Gaussian output 側の振動 mode 番号 |
| coord_id | DD2 内部座標 ID |
| coord_code | VEDA/DD2 の座標解釈コード。例: `s`, `k`, `v` |
| STRE | Stretching、伸縮座標 |
| BEND | Bending、変角座標 |
| TORS | Torsion、ねじれ座標 |
| target | 追跡対象として指定した内部座標群 |
| total_target_PED | ある mode に含まれる target 座標群の PED 合計 |
| weighted_mean_freq | PED 値を重みとして計算した平均周波数 |

---

## 14. 最小ワークフローまとめ

急いで解析する場合は、以下だけ実行してください。

1. `Files / Precheck` でファイルを選択。
2. `Load / Precheck` を実行。
3. `Coordinate Browser` で `STRE` と金属 atom index で絞り込み。
4. 目的の M–L 伸縮を選んで `Add selected to target`。
5. `Run Analysis` で周波数範囲を指定。
6. `RUN TARGET ANALYSIS`。
7. `target_summary_by_mode` を開き、`total_target_PED` が大きい mode を確認。


---

## 15. `target_summary_by_coord` の列の意味と `top_modes` の読み方

`target_summary_by_coord` は、指定した target 内部座標ごとに、どの振動 mode にどの程度分散して現れているかを要約する CSV です。

たとえば金属錯体で Co–N 伸縮、Ga–O 伸縮、M–Cl 伸縮などを target にした場合、各内部座標について「最大寄与を示す mode」「指定周波数範囲内での合計 PED」「PED で重み付けした平均周波数」「主な出現 mode」がまとめられます。

### 15.1 主な列の意味

| 列名 | 意味 |
|---|---|
| `mode_veda_at_max` | その内部座標の PED 寄与が最大になった VEDA 側の mode 番号 |
| `freq_qc_at_max` | その最大寄与 mode に対応する QC output 側の振動数。単位は cm^-1 |
| `freq_veda_at_max` | その最大寄与 mode の VEDA 側の振動数。単位は cm^-1 |
| `sum_PED_in_range` | 指定した周波数範囲内で、その内部座標が持つ PED 寄与の合計 |
| `weighted_mean_freq` | PED 値を重みとして計算した平均振動数 |
| `n_modes_detected` | しきい値以上の PED を持つ mode として検出された数 |
| `top_modes` | その内部座標が比較的大きく含まれる mode を、PED 寄与の大きい順に並べた要約 |

`mode_veda_at_max` は、その内部座標が最も強く現れる VEDA mode を示します。たとえば、ある M–L 伸縮が複数の mode に分裂している場合、その中で最も PED % が大きい mode の VEDA 番号が入ります。

`freq_qc_at_max` は、ORCA または Gaussian などの QC output 側で見た振動数です。スペクトルとの比較では、通常こちらの値を主に見ます。

`freq_veda_at_max` は、VEDA 側で読まれた振動数です。`freq_qc_at_max` と近い値になるのが理想ですが、VEDA mode と QC mode はプログラム内で振動数ベースに対応付けているため、完全に一致しないことがあります。

`sum_PED_in_range` は、指定した周波数範囲内にある mode だけを対象に、その内部座標の PED % を足し合わせた値です。配位結合伸縮が指紋領域の複数 mode に分裂している場合、この値が重要です。

`weighted_mean_freq` は、PED 値を重みとして計算した平均振動数です。概念的には次の式です。

```text
weighted_mean_freq = Σ(freq × PED) / Σ(PED)
```

PED 寄与が大きい mode ほど平均値に強く反映されます。そのため、単純平均ではなく「その内部座標の振動成分の重心がどの周波数付近にあるか」を見る指標になります。

`n_modes_detected` は、その内部座標が条件を満たして検出された mode 数です。金属錯体の配位結合伸縮では、配位子変形や骨格変形と混ざるため、この値が大きくなることがあります。

---

### 15.2 `top_modes` の基本形式

`top_modes` には、次のような形式で mode 情報が並びます。

```text
QC107/V271@594.0:15.1% (rank 1)
```

これは次の意味です。

| 部分 | 意味 |
|---|---|
| `QC107` | QC output 側の mode 107 |
| `V271` | VEDA 側の mode 271 |
| `@594.0` | QC 側の振動数 594.0 cm^-1 |
| `15.1%` | この内部座標の PED 寄与 |
| `rank 1` | その mode の中で、この内部座標が PED 寄与第1位であること |

したがって、

```text
QC107/V271@594.0:15.1% (rank 1)
```

は、

```text
QC mode 107、VEDA mode 271、594.0 cm^-1 の振動では、
この内部座標が 15.1% 含まれており、
その mode 内で最も大きい PED contributor である。
```

という意味です。

---

### 15.3 `top_modes` の読み方の例

例として、次のような `top_modes` が出力されたとします。

```text
QC107/V271@594.0:15.1% (rank 1);
QC113/V265@635.8:12.9% (rank 1);
QC116/V262@743.5:6.2% (rank 4);
QC15/V363@72.6:5.5% (rank 5);
QC71/V307@350.7:5.2% (rank 3);
QC103/V275@570.8:4.4% (rank 6);
QC78/V300@412.4:3.7% (rank 3);
QC65/V313@328.2:3.7% (rank 4);
QC76/V302@391.1:3.6% (rank 4);
QC91/V287@480.3:3.5% (rank 10)
```

この場合、対象の内部座標は複数の mode に分散しています。

| 表記 | 解釈 |
|---|---|
| `QC107/V271@594.0:15.1% (rank 1)` | 594.0 cm^-1 の mode で 15.1%。この mode の主成分 |
| `QC113/V265@635.8:12.9% (rank 1)` | 635.8 cm^-1 の mode で 12.9%。これも主成分 |
| `QC116/V262@743.5:6.2% (rank 4)` | 743.5 cm^-1 の mode に 6.2%。第4位成分 |
| `QC15/V363@72.6:5.5% (rank 5)` | 72.6 cm^-1 の低波数 mode に 5.5%。第5位成分 |
| `QC91/V287@480.3:3.5% (rank 10)` | 480.3 cm^-1 の mode に 3.5%。ただし rank 10 なので通常の上位6件表では見落とされる可能性がある |

この例では、特に大きい寄与は以下です。

```text
594.0 cm^-1: 15.1%
635.8 cm^-1: 12.9%
743.5 cm^-1: 6.2%
```

したがって、この内部座標の主要な振動成分は 594–636 cm^-1 付近に強く、さらに 743.5 cm^-1 にも分裂して現れていると解釈できます。

一方で、72.6 cm^-1、328.2 cm^-1、350.7 cm^-1、391.1 cm^-1、412.4 cm^-1、480.3 cm^-1 などにも数 % 程度含まれています。これは、金属錯体の骨格変形、配位子変形、低波数の collective mode などに同じ内部座標成分が混ざっている可能性を示します。

---

### 15.4 解釈時に見るべきポイント

`top_modes` を見るときは、PED % だけでなく、次の点を合わせて確認してください。

1. `PED_value` が大きいか
2. `rank` が高いか
3. `IR_intensity` が強いか
4. 周波数が化学的に妥当な領域にあるか

たとえば、

```text
QC107/V271@594.0:15.1% (rank 1)
QC113/V265@635.8:12.9% (rank 1)
```

は、PED も大きく rank も 1 なので、その内部座標にとって重要な mode です。

一方、

```text
QC91/V287@480.3:3.5% (rank 10)
```

は、対象内部座標を含んではいますが、その mode の主成分ではありません。補助的な混合成分として扱うのがよいです。

従来の `PED1` から `PED6` までの標準表では、`rank 10` のような寄与は表示されません。しかし target tracking では、指定した内部座標を直接追跡するため、rank が低い寄与も検出できます。

---

### 15.5 まとめ

`target_summary_by_coord` は、内部座標ごとに次のことを確認するための表です。

```text
その内部座標が最大 PED を示す mode はどれか
その最大寄与 mode の周波数はいくつか
指定周波数範囲内で合計どれだけ PED があるか
PED 重み付き平均周波数はどこか
何個の mode に分裂して現れているか
どの mode に強く含まれるか
```

配位結合伸縮が指紋領域で多数の normal mode に分裂している場合は、`freq_qc_at_max` だけでなく、`sum_PED_in_range`、`weighted_mean_freq`、`n_modes_detected`、`top_modes` を合わせて見ると、全体像を把握しやすくなります。
