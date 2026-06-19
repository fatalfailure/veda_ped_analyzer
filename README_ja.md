# veda_ped_analyzer

`veda_ped_analyzer` は、**VEDA** の出力ファイル（`.ved`, `.dd2`）から **PED（Potential Energy Distribution）** を解析し、**ORCA** または **Gaussian** の振動解析 output と対応付けて CSV に整理する Python GUI ツールです。

従来の mode 中心 PED 表に加えて、v1.1.0 では **target coordinate tracking** 機能を追加しました。これは、金属錯体の金属–配位子伸縮のように、特定の内部座標成分が指紋領域の複数 normal mode に分裂して現れる場合に有用です。

## バージョン

現在の公開版: **v1.1.0 - Target Coordinate Tracking**

## リポジトリ

GitHub: https://github.com/fatalfailure/veda_ped_analyzer

## 主な機能

- VEDA PED 解析用 GUI
- ORCA / Gaussian 振動解析 output の読み取り
- 振動数に基づく VEDA mode と QC mode の対応付け
- DD2 内部座標を一覧・検索する Coordinate Browser
- 特定の内部座標を追跡する target coordinate tracking
- 金属–配位子伸縮座標の自動抽出
- 従来型の top-N PED table 出力
- rank 7 以下の寄与も検索できる long-format PED table 出力
- target hits 出力
- target summary by mode 出力
- target summary by coordinate 出力
- Excel ヒートマップ用 target matrix 出力
- `alternative_k` / `alternative_v` の任意出力
- 前回の GUI 設定を JSON に保存・復元

## 入力ファイル

必須:

- VEDA `.ved`
- VEDA `.dd2`
- 量子化学計算の振動解析 output:
  - ORCA: `.out`
  - Gaussian: `.log` または `.out`

推奨:

- `.fmu`（atom index と元素記号の対応に使用）

`.fmu` がない場合、QC output の座標ブロックから元素記号の対応を推定します。

## 実行方法

```bash
python veda_ped_analyzer.py
```

GUI には以下のタブがあります。

- `Files / Precheck`
- `Coordinate Browser`
- `Target Definition`
- `Run Analysis`
- `Results Preview`
- `User Guide`

## 基本的な解析手順

1. `Files / Precheck` で `.ved`, `.dd2`, 任意の `.fmu`, QC output（`.out` / `.log`）を選択します。
2. `Load / Precheck` を押し、PED block、DD2 座標、QC 振動数、mode mapping が読めていることを確認します。
3. `Coordinate Browser` で目的の内部座標を探します。
4. 目的の内部座標を target に追加するか、金属–配位子伸縮の自動抽出を使います。
5. `Run Analysis` で PED しきい値と周波数範囲を指定します。
6. `RUN TARGET ANALYSIS` を押します。
7. `Results Preview` または出力 CSV を確認します。

## 出力ファイル

出力ファイル名は、入力 `.ved` のファイル名を基準に作られます。

### 標準出力

- `*_PED_table_standard.csv`  
  従来型の mode 中心 PED 表です。各 mode の上位 PED contributor を出力します。

- `*_PED_terms_long_standard.csv`  
  PED contributor を mode × 内部座標の縦長形式で保存します。上位 N 件に入らない target 座標を探すために有用です。

- `*_target_hits_standard.csv`  
  指定した target 座標が検出された mode を一覧します。

- `*_target_summary_by_mode_standard.csv`  
  mode ごとに target 座標群の PED 合計をまとめます。分裂した金属–配位子伸縮を探すための主出力です。

- `*_target_summary_by_coord_standard.csv`  
  内部座標ごとに、どの mode に強く現れるかをまとめます。

- `*_target_matrix_standard.csv`  
  行が振動 mode、列が target 座標の行列形式です。

- `*_coordinates_lookup.csv`  
  DD2 内部座標の lookup 表です。

### alternative 座標出力

`alternative_k` / `alternative_v` はデフォルトでは出力されません。必要な場合のみ、`Run Analysis` タブで `Include alternative coordinate sets (k/v)` を ON にしてください。

ON にした場合、以下のようなファイルも追加で出力されます。

- `*_PED_table_alternative_k.csv`
- `*_PED_terms_long_alternative_k.csv`
- `*_target_summary_by_mode_alternative_k.csv`
- `*_PED_table_alternative_v.csv`
- `*_PED_terms_long_alternative_v.csv`
- `*_target_summary_by_mode_alternative_v.csv`

通常は `standard` のみで解析を始め、standard で目的の内部座標を追跡しにくい場合に alternative を確認する運用を推奨します。

## 重要な列

### `*_PED_table_standard.csv`

- `mode_veda`, `freq_veda`
- `mode_qc`, `freq_qc`, `delta_freq`, `abs_delta_freq`
- `irrep`
- `IR_intensity`
- `PED1_*`, `PED2_*`, ... 指定した top-N まで
- `total_target_PED`
- `top_target_terms`

### `*_target_summary_by_mode_standard.csv`

- `mode_qc`, `freq_qc`
- `IR_intensity`
- `total_target_PED`
- `max_target_PED`
- `n_target_coords_detected`
- `best_target_rank`
- `top_target_terms`

### `*_target_summary_by_coord_standard.csv`

- `coord_id`, `label`
- `max_PED`
- `mode_qc_at_max`, `mode_veda_at_max`
- `freq_qc_at_max`, `freq_veda_at_max`
- `sum_PED_in_range`
- `weighted_mean_freq`
- `n_modes_detected`
- `top_modes`

## 設定 JSON とログ

前回使用した GUI 設定は、通常以下に保存されます。

```text
veda_ped_analyzer.json
```

実行フォルダに書き込めない場合は、ホームディレクトリに保存されます。

ログは通常、以下に保存されます。

```text
veda_ped_analyzer.log
```

これらのローカル `.json` / `.log` ファイルは通常 Git に含めないでください。

## マニュアル

- 英語版: `veda_ped_analyzer_manual.md`
- 日本語版: `veda_ped_analyzer_manual_ja.md`

## 引用情報

引用用メタデータは `CITATION.cff` に記載しています。GitHub release を作成して Zenodo でアーカイブした後、発行された DOI を `CITATION.cff` に追記し、必要に応じて README に DOI badge を追加してください。

## よくある Windows エラー: Permission denied

CSV 保存時に `[Errno 13] Permission denied` が出る場合、主な原因は以下です。

- 出力 CSV を Excel で開いたままにしている
- 出力先フォルダが書き込み禁止である
- クラウド同期フォルダの制限がある

Excel を閉じ、デスクトップやドキュメントなど書き込み可能な出力先を選んでください。

## ライセンス

MIT License（`LICENSE` 参照）
