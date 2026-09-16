## Bambu Filament Path 1.1.2

**0.4mmノズルのデータも、同じアドオンで扱えます。** 経路ごとの `LINE_WIDTH` / `LAYER_HEIGHT` を使うため、0.4mm専用版への切り替えは不要です。QIDIStudioのヘッダー名の認識と、合成データによる回帰テストを追加しました。さらに、同色・同一平面・同じ向きの重複面の整理を底面にも適用し、下から見せるロゴなどに現れる黒い斑点に対処しています。元の座標を動かすオフセットは加えません。線幅・層厚の読み取り方法と初期設定はv1.1.1と共通です。

QIDIStudio 02.07.02.60のQ2・0.4mmノズル設定から書き出した40mm・15層チップ1個を、v1.1.2のBlenderインポーターで読み込み、Blender 5.2.1 LTSでロゴ側をレンダリングして確認しました。同じカメラ・照明の比較で、底面の重複による黒い斑点が解消したことを確認しています。可変線幅、狭い隙間埋め、Bridgeの `LAYER_HEIGHT: 0.4` を保持します。確認範囲はこの注釈付き出力であり、QIDI全機種・全設定への対応保証ではありません。実モデルやG-codeは公開していません。

Assetsの **`Bambu_Filament_Path-1.1.2.zip`** を、Blenderの **Preferences → Add-ons → Install from Disk** からインストールしてください。既存版を上書きした後は、Blenderを終了して再起動し、G-codeを再インポートします。

---

**The same add-on handles data sliced with a 0.4 mm nozzle.** Dimensions come from each path's `LINE_WIDTH` / `LAYER_HEIGHT`, so a separate nozzle-specific edition is unnecessary. This patch recognizes the QIDIStudio header and adds generated regression fixtures. It also removes duplicate coverage on same-material, exactly coplanar, same-facing bottom surfaces to address dark specks on bed-side logos, without applying a coordinate offset. Width/height interpretation and import defaults remain the same as v1.1.1.

One real 40 mm, 15-layer chip exported by QIDIStudio 02.07.02.60 using the Q2 / 0.4 mm nozzle profile was imported with the v1.1.2 Blender importer and verified with a logo-side render in Blender 5.2.1 LTS. A comparison under the same camera and lighting confirmed that the black specks caused by duplicate bottom surfaces were removed. Variable widths, narrow gap infill, and Bridge paths annotated with `LAYER_HEIGHT: 0.4` are retained. This checks that annotated output, not every QIDI printer or profile. Private models and G-code are not distributed.

Install **`Bambu_Filament_Path-1.1.2.zip`** through **Preferences → Add-ons → Install from Disk**, then quit and restart Blender before re-importing. Existing installations can be updated in place.

[使い方 / Documentation](https://github.com/Psych0h3ad/bambu-filament-path-blender) · [開発を応援する / GitHub Sponsors](https://github.com/sponsors/Psych0h3ad)
