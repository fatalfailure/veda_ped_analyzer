# veda_ped_analyzer

`veda_ped_analyzer` は、**VEDA** の出力ファイル（`.ved`, `.dd2`）から
**PED（Potential Energy Distribution）** を解析し、CSV 形式で整理する
Python GUI ツールです。
必要に応じて **ORCA** や **Gaussian** の出力を読み取り、
振動モードとの対応付けを行います。

## 入力ファイル

必須:
- VEDA `.ved`
- VEDA `.dd2`
- 量子化学計算出力:
  - ORCA: `.out`
  - Gaussian: `.log` または `.out`

任意:
- `.fmu`（原子ラベルを改善するために使用）

## 出力ファイル

- `*_PED_table.csv`  
  振動モードごとの PED 上位寄与成分一覧。
- `*_coordinates_lookup.csv`  
  内部座標と主に寄与するモードの要約（`top_mode_terms`）。

### `*_PED_table.csv` の主要カラム

- `mode_veda`, `freq_veda`
- `mode_qc`, `freq_qc`, `delta_freq`, `abs_delta_freq`
- `irrep`
- `IR_intensity`（ORCA/Gaussian の赤外強度）
- `PED1_*` … `PED6_*`

## 実行方法

```bash
python veda_ped_analyzer.py
```

Windows では `veda_ped_analyzer.pyw` を使用すると
コンソールを表示せずに起動できます。

## よくあるエラー（Windows）

### Permission denied エラー

原因:
- CSV を Excel で開いたまま
- 出力先が書き込み禁止フォルダ（例: C:\ 直下）
- OneDrive 等の同期フォルダ制限

対処:
- Excel を閉じる
- デスクトップやドキュメントなど書き込み可能な場所を選択

## ライセンス

MIT License（`LICENSE` 参照）
