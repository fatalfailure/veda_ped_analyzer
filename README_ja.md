# veda_ped_analyzer

**現在のバージョン:** v1.1.1  
**リポジトリ:** https://github.com/fatalfailure/veda_ped_analyzer

`veda_ped_analyzer` は、**VEDA** の出力ファイル（`.ved`, `.dd2`）から **PED（Potential Energy Distribution）** を解析し、CSV 形式で整理する Python GUI ツールです。必要に応じて **ORCA** または **Gaussian** の振動解析 output を読み取り、VEDA mode と QC output 側 mode を対応付けます。

このソフトは、**金属錯体専用ではなく、汎用的な PED 解析アプリ**として設計しています。v1.1.x では、任意の内部座標を target として指定し、その PED 寄与を全 mode にわたって追跡する機能を追加しました。金属–配位子伸縮の自動検出は、錯体解析用の補助機能であり、デフォルトの解析モードではありません。

## 主な機能

- VEDA `.ved` / `.dd2` の GUI 解析
- ORCA / Gaussian の振動解析 output 読み取り
- 周波数に基づく VEDA mode と QC mode の対応付け
- 従来型の mode 中心 top-N PED table 出力
- DD2 内部座標を一覧・検索する Coordinate Browser
- 任意の内部座標を追跡する target-coordinate tracking
- 金属–配位子伸縮の任意自動検出補助
- rank 7 以下も検索できる long-format PED table 出力
- target hits、target summary by mode、target summary by coordinate、target matrix 出力
- `alternative_k` / `alternative_v` 座標解釈の任意出力。デフォルトでは OFF

## 必要環境

- Python 3.9 以降を推奨
- `pandas`
- 標準ライブラリ `tkinter`

必要なパッケージは以下でインストールできます。

```bash
pip install pandas
```

## 入力ファイル

必須:

- VEDA `.ved`
- VEDA `.dd2`
- 量子化学計算の振動解析 output:
  - ORCA: `.out`
  - Gaussian: `.log` または `.out`

任意:

- `.fmu`。元素ラベルを改善するために使用します。

## 実行方法

```bash
python veda_ped_analyzer.py
```

## Coordinate Browser の初期設定

Coordinate Browser は、初期状態で以下のフィルタが選択されます。

- **Coordinate set:** `s - standard`
- **Group:** `STRE - Stretching`

標準の伸縮座標から確認を始めやすくするためです。Coordinate set のプルダウンに表示される `s`, `k`, `v` は VEDA/DD2 の座標解釈コードです。

| 表示 | 意味 |
|---|---|
| `s - standard` | 標準の内部座標解釈 |
| `k - alternative` | 代替内部座標解釈 |
| `v - alternative2` | 2つ目の代替内部座標解釈 |
| `(any)` | 利用可能な座標解釈をすべて表示 |

## `target_set_name` の意味

出力 CSV の `target_set_name` は、選択した内部座標群に付ける **ユーザー定義のラベル**です。計算モードを意味するものではなく、金属錯体専用であることも意味しません。

デフォルト値は以下です。

```text
target_coordinates
```

たとえば、`ring_CC_stretches`, `carbonyl_modes`, `Co_N_stretches` など、解析対象に合わせて自由に変更できます。金属–配位子伸縮の自動検出ボタンを使った場合は、その target set を表すラベルとして `metal_ligand_stretch` が使われることがあります。

## 出力ファイル

入力が `sample.ved` の場合、標準設定では以下のようなファイルが出力されます。

- `sample_PED_table_standard.csv`  
  mode 中心の top-N PED 表。
- `sample_PED_terms_long_standard.csv`  
  PED contributor を縦長形式で保存する検索用テーブル。
- `sample_target_hits_standard.csv`  
  target 座標が各 mode にどの程度含まれるかを示す表。
- `sample_target_summary_by_mode_standard.csv`  
  mode ごとに target 座標群の PED 合計を示す表。
- `sample_target_summary_by_coord_standard.csv`  
  内部座標ごとに、どの mode に強く現れるかをまとめた表。
- `sample_target_matrix_standard.csv`  
  行が mode、列が target coord_id の行列形式。
- `sample_coordinates_lookup.csv`  
  DD2 内部座標の lookup table。

### alternative 座標出力

`alternative_k` / `alternative_v` はデフォルトでは出力されません。DD2/VEDA の代替内部座標解釈を確認したい場合のみ、Run Analysis タブの **Include alternative coordinate sets (k/v)** を ON にしてください。

## ドキュメント

- 英語マニュアル: `veda_ped_analyzer_manual.md`
- 日本語マニュアル: `veda_ped_analyzer_manual_ja.md`
- 変更履歴: `CHANGELOG.md`
- 引用メタデータ: `CITATION.cff`

## よくあるエラー: Permission denied

CSV 保存時に `[Errno 13] Permission denied` が出る場合、主な原因は以下です。

- 出力 CSV を Excel で開いたまま
- 出力先が書き込み禁止フォルダ
- OneDrive などの同期フォルダがファイルをロックしている

Excel を閉じ、Desktop や Documents など書き込み可能な場所を出力先に指定してください。

## ライセンス

MIT License（`LICENSE` 参照）
