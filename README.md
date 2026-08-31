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

## Live2D録画

OBSにVTube Studioのウィンドウキャプチャを1つ設定し、OBS WebSocketを有効にしてから、`.env`で`LIVE2D_RECORD=true`にします。OBSのWebSocket設定でパスワードを設定した場合は`OBS_PASSWORD`にも設定してください。

VTube StudioのPlugin APIを許可すると、初回実行時に認証確認が表示されます。許可後はMayoiの読み込み、録画開始・停止、音声との合成を自動で行います。

生成した音声の音量を解析し、VTube Studioの`ParamMouthOpenY`へ送るため、マイクなしで口パクします。モデルによって口パラメータ名が違う場合は`VTS_MOUTH_PARAMETER`を変更してください。

## 注意

YouTubeへの自動投稿はまだ接続していません。動画を1本生成できることを確認してから、YouTube OAuth投稿を追加します。
