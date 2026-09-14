## Bambu Rounded Beads 1.0.0

Bambu StudioのG-codeから、積層と押し出し端の丸みを持つメッシュを作るBlenderアドオンです。

**下のAssetsから `Bambu_Rounded_Beads-1.0.0.zip` をダウンロードし、BlenderのPreferences → Add-ons → Install from Diskでインストールしてください。** 自動生成されるSource code ZIPとは別です。

- 線幅・積層ピッチ・フィラメント色をG-codeから取得
- 実際の開いた経路端を丸め、途中の分割点には余計な膨らみを追加しない
- Windows版Blender 5.2.1 LTSでインストール・読み込み確認済み
- 日英READMEとGPL-3.0-or-laterライセンスを同梱

レンダリング用の形状近似です。樹脂の流動・融着のシミュレーションではありません。

---

Create Blender meshes with visible printed layers and rounded extrusion terminals from annotated Bambu Studio G-code.

Download the **`Bambu_Rounded_Beads-1.0.0.zip` release asset** and use Blender Preferences → Add-ons → Install from Disk. The automatic source-code archives are not the installable asset.

Preserves source dimensions and filament IDs, rounds real open ends, and avoids expanding caps at continuous-path subdivisions. Tested on Blender 5.2.1 LTS for Windows. Includes Japanese/English instructions and GPL-3.0-or-later licensing.

This is illustrative rendering geometry, not fused-polymer simulation.

[使い方 / Documentation](https://github.com/Psych0h3ad/bambu-rounded-beads-blender) · [開発を応援する / GitHub Sponsors](https://github.com/sponsors/Psych0h3ad)
