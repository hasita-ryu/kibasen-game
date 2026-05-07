# 眠った吸血鬼を運べ

MESHの振動センサー・明るさセンサー入力をキー入力として受け取り、眠っている吸血鬼のHPを減らしていくPython製の小さなゲームです。

## 実行方法

```sh
/usr/local/bin/python3 vampire_hp_game.py
```

## 操作

- `V`: MESH 振動センサー入力として扱う。HP -2
- `L`: MESH 明るさセンサー入力として扱う。HP -4
- `Space`: 手動ダメージ。HP -5
- `Q`: 現在のHPで停止
- `R`: HPを100に戻して再開

## 必要なもの

- Python 3
- pygame

## ファイル構成

- `vampire_hp_game.py`: ゲーム本体
- `assets/`: 背景と吸血鬼の画像素材
- `clean_sprite_edges.py`: 生成画像の白い縁を透明化するための補助スクリプト
