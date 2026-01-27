# ユーザーマニュアル – veda_ped_analyzer

## 1. 概要

本プログラムは VEDA による PED 出力を解析し、CSV を生成します。
必要に応じて ORCA または Gaussian の出力を読み取り、
振動モードの対応付けを行います。

## 2. 入力ファイル

### 2.1 VEDA `.ved`
PED（および任意で TED）行列と周波数を含みます。

### 2.2 VEDA `.dd2`
内部座標定義ファイル（PED 列のラベル付けに使用）。

### 2.3 量子化学計算出力

取得する情報:
- 振動数
- IR 強度
- 対称種ラベル（あれば）
- 原子情報

対応形式:
- ORCA `.out`
- Gaussian `.log` / `.out`

## 3. 出力ファイル

### 3.1 `*_PED_table.csv`

各行が 1 つの振動モードに対応します。

主なカラム:
- `mode_veda`, `freq_veda`
- `mode_qc`, `freq_qc`
- `delta_freq`, `abs_delta_freq`
- `irrep`
- `IR_intensity`
- `PED1_*` … `PED6_*`

### 3.2 `*_coordinates_lookup.csv`

各内部座標を 1 行でまとめます。
`top_mode_terms` は主に寄与するモードの要約です。

## 4. 解釈上の注意

- PED は 100% に正規化されています。
- 対称性の高い分子ではモード混合が一般的です。
- 周波数差が大きい場合は必ず妥当性を確認してください。

## 5. トラブルシューティング

- CSV 保存時にエラーが出る場合、Excel を閉じてください。
- `.ved` と QC 出力が同一計算条件か確認してください。
