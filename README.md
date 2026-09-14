# Bambu Rounded Beads for Blender

[English](README.en.md) · [ダウンロード](https://github.com/Psych0h3ad/bambu-rounded-beads-blender/releases/latest) · [GitHub Sponsors](https://github.com/sponsors/Psych0h3ad)

3Dプリントしたものを、それっぽくレンダリングしたい。積層も、樹脂が止まるところの丸みも欲しい。そんなときのために作ったBlenderアドオンです。

Bambu Studioから書き出したG-codeを読み、線幅・積層ピッチ・フィラメント色に沿った樹脂の断面と、押し出し経路の端の丸みをメッシュにします。MakerChipのレンダリング記事用に作りましたが、対応する注釈付きG-codeなら別のモデルにも使えます。

## インストール

1. [Releases](https://github.com/Psych0h3ad/bambu-rounded-beads-blender/releases/latest)から **Bambu_Rounded_Beads-1.0.0.zip** をダウンロードします。GitHubの「Source code (zip)」とは別です。
2. Blenderの **Edit → Preferences → Add-ons** を開きます。
3. 右上のメニューから **Install from Disk** を選び、ダウンロードしたZIPをそのまま指定します。
4. **Bambu Rounded Beads** を有効にします。

Blenderに同梱のNumPyを使うため、通常は追加インストール不要です。Windows版Blender **5.2.1 LTS** で、ZIPのインストール・有効化・実際の読み込みを確認しています。アドオンが宣言する最低バージョンは4.5ですが、全バージョン・全OSでの動作確認ではありません。

## 使い方

1. Bambu Studioで、まず**オブジェクトが1個だけのプレート**をスライスし、注釈を含む `.gcode` を書き出します。対応確認はBambu Studio 2.8.2.61です。
2. BlenderをObject Modeにし、**File → Import → Bambu G-code — Rounded Beads (.gcode)** を選びます。
3. G-codeを選びます。オブジェクトが1個なら **Object Label** は空欄で構いません。
4. **Center XY / Ground Z** と **Match Native Black** を必要に応じて設定し、**Import Rounded Beads** を押します。
5. `MakerChip_Rounded` が追加されます。元のOBJなどが重なっている場合は、元モデルをビューポートとレンダーの両方で非表示にします。
6. カメラ・ライト・マテリアルを調整してレンダリングします。既存シーンのカメラや照明は変更しません。

### 読み込み設定

| 設定 | 内容 |
| --- | --- |
| Object Label | 複数のオブジェクトを含むG-codeから1個を選ぶ識別子。空欄で複数あると、候補をエラーに表示します。 |
| Center XY / Ground Z | 生成後の境界をXY中央へ移動し、最下点をZ=0に置きます。mmはBlenderのmへ変換します。 |
| Match Native Black | 元データの黒 `#000000` を、BambuのOBJプレビューと比較しやすい `#333333` で表示します。元の色もマテリアルのプロパティに残ります。 |

ノズル径を入力する設定はありません。断面はG-code内の **LINE_WIDTH / LAYER_HEIGHT** を使います。ノズル径と線幅は同じ意味ではありません。

## どこを丸めるのか

- 樹脂の断面を、線幅とレイヤー高さから作ります。通常は10点の扁平な断面です。
- 実際に開いている経路の端に、3段のリングからなるドームを追加します。伸びる量は、その場所の線幅の半分です。
- 同じ経路の途中にある線幅変化や、メッシュ化のための分割点には、余計な丸い膨らみを作りません。
- 閉じた経路には端のドームを追加しません。
- 白いGyroidのような露出したインフィルも含め、対応する押し出し区分とフィラメント色を取り込みます。
- 直線経路の簡略化は行いません。G2/G3のXY円弧は最大0.005mmの弦誤差を基準に分割します。

これは**レンダリング用の形状近似**です。樹脂の流動、融着、体積保存を計算するものではありません。別々の樹脂メッシュは重なる場合があります。ネイティブOBJをベベルする処理ではなく、G-codeから別のメッシュを作る方式です。

## 対応範囲と重さ

`CONFIG_BLOCK` 内の `filament_colour`、オブジェクト識別子、`FEATURE`、`LINE_WIDTH`、`LAYER_HEIGHT` といったBambuの注釈が必要です。3MFやOBJを直接読み込む機能ではありません。一般的なG-code全形式、G18/G19などの別平面円弧、R形式の円弧への対応は保証していません。

40mm・30層のチップ1個で約451万頂点・485万面になる例があります。形状やPCによって読み込み時間とメモリ使用量が大きく変わります。最初は1個で試してください。

G-codeはテキストとして読み取ります。プリンターへの送信、ネットワーク通信、元ファイルの書き換えは行いません。生成オブジェクトには出典のファイル名を保存し、ユーザーの絶対パスは保存しません。

## 開発・検証

PythonとNumPyがある環境で、合成した小さな経路のテストを実行できます。テスト用G-codeは実行時に作り、実モデルやプリンタープロファイルはリポジトリに含めていません。

```sh
python -m unittest discover -s tests -v
python tools/build_release.py
```

ZIPは `dist/` に作成されます。Blenderの実インポーターを含むテストは、次のコマンドで実行できます。

```sh
blender --background --factory-startup --python tests/blender_smoke.py
```

公開版のテストでは、開いた端と閉ループ、線幅変化の連続性、面の向きと閉じたトポロジー、色、スケール、既存シーンの保持を確認します。

## 応援してもらえると嬉しいです

こういう地味に欲しいツールを、ちまちま作っています。役に立ったら、[GitHub Sponsors](https://github.com/sponsors/Psych0h3ad)で開発を応援してもらえると嬉しいです。スポンサー募集中です。

不具合や改善案は[Issues](https://github.com/Psych0h3ad/bambu-rounded-beads-blender/issues)へどうぞ。再現データを添付する場合は、ご自身が公開できるものだけにしてください。

## ライセンス

Copyright © 2026 Psych0h3ad. **GPL-3.0-or-later**。全文は[LICENSE](LICENSE)を参照してください。Bambu LabおよびBlender Foundationによる公式アドオンではありません。
