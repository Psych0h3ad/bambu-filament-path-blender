## Bambu Rounded Beads 1.1.0

押し出しが止まる端に加えて、**外壁・内壁の曲がりも丸く**なりました。初期設定のままで、積層の断面・端・長い曲線を滑らかにレンダリングできます。

- 断面26点（円形・縦長楕円は24点）、端11リング、壁の円弧64分割相当以上へ高精細化。
- G2/G3円弧の弦誤差を0.005mmから0.001mmへ改善。元の移動終点・線幅・積層ピッチを維持します。
- 重複する平らな上面が黒い斑点に見える問題を修正。

下のAssetsから **`Bambu_Rounded_Beads-1.1.0.zip`** をダウンロードし、Blenderの **Preferences → Add-ons → Install from Disk** でインストールしてください。

**更新後はBlenderを終了して再起動し、G-codeを再インポートします。** 前のメッシュは自動更新されません。元のOBJや古い読み込み結果は、Outlinerの目とカメラを両方オフにして重ならないようにしてください。

高精細な形状はメモリを使います。まず1個のオブジェクトで試してみてください。

---

**Outer and inner wall bends are now rounded, alongside genuine extrusion ends.** The defaults produce smoother bead sections, terminals, and long curves.

- Higher geometric resolution: 26-point sections (24 for circles/vertical ellipses), 11 intermediate terminal rings, and wall arcs equivalent to at least 64 segments per circle.
- Refine G2/G3 chord error from 0.005 mm to 0.001 mm while retaining source move endpoints, line widths, and layer heights.
- Fix dark specks caused by overlapping flat top faces.

Download **`Bambu_Rounded_Beads-1.1.0.zip`** below and install through **Preferences → Add-ons → Install from Disk**.

**Quit and restart Blender after updating, then re-import the G-code.** Existing meshes are not updated automatically. Disable both the eye and camera icons for overlapping native or older imported objects. High resolution requires more memory; start with one object.

Includes Japanese/English documentation and GPL-3.0-or-later licensing. This is rendering geometry, not a polymer-flow simulation.

[使い方 / Documentation](https://github.com/Psych0h3ad/bambu-rounded-beads-blender) · [開発を応援する / GitHub Sponsors](https://github.com/sponsors/Psych0h3ad)
