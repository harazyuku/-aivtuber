# 自動AI VTuber

マイクを使わず、台本生成から音声付き動画の作成までを自動で行う別プロジェクトです。

## 現在できること

1. Geminiで30〜45秒の台本を生成
2. AivisSpeechで音声ファイルを生成
3. アバター画像と音声をFFmpegで縦動画に合成

## 準備

```bash
cp .env.example .env
```

`.env`にGemini APIキーを設定し、`assets/avatar.png`にアバター画像を置きます。AivisSpeechを起動してから実行してください。

```bash
python3 main.py
```

動画は`output/`に作成されます。

## 注意

この初版は安定して1本を作るため、Live2Dのリアルタイム録画とYouTube投稿はまだ接続していません。次の段階でVTube Studio/OBS録画とYouTube OAuth投稿を追加します。
