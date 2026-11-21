# Icon assets

Composed from Material Design Icons glyphs (Apache 2.0, © Pictogrammers /
Austin Andrews & contributors): `television` (bezel) and `image-multiple`
(art on screen). The screen gradient and squircle are original.
Licensed under Apache 2.0; the master SVG is kept here for reproducibility.

Rendered with qlmanage (WebKit, keeps gradients) + ImageMagick rounded mask.

Regenerate:

    qlmanage -t -s 1024 -o /tmp assets/icon-master.svg
    magick -size 1024x1024 xc:none -fill white \
      -draw "roundrectangle 0,0 1023,1023 185,185" /tmp/mask.png
    magick /tmp/icon-master.svg.png /tmp/mask.png -alpha off \
      -compose CopyOpacity -composite /tmp/master.png
    for spec in "icon.png:256" "icon@2x.png:512" "logo.png:128" "logo@2x.png:256"; do
      magick /tmp/master.png -resize "${spec##*:}x${spec##*:}!" "assets/${spec%%:*}"
    done

The same files are submitted to home-assistant/brands under
`custom_integrations/samsung_frame_art/` (that is what the Marketplace shows).
