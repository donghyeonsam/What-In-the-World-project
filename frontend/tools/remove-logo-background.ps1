# Reproducible white-matte removal for the original 1860 x 411 header logo.
# Keeps the original file, dimensions and colored foreground pixels.
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.Drawing.Drawing2D;

public static class HeaderLogoMatte {
    static int Min(Color c) { return Math.Min(c.R, Math.Min(c.G, c.B)); }
    static int Clamp(double value) { return (int)Math.Max(0, Math.Min(255, Math.Round(value))); }
    public static void Convert(string source, string destination) {
        using (var original = new Bitmap(source))
        using (var output = new Bitmap(original.Width, original.Height, PixelFormat.Format32bppArgb))
        using (var letter = new GraphicsPath()) {
            if (original.Width != 1860 || original.Height != 411)
                throw new InvalidOperationException("This mask is specific to the original 1860 x 411 logo.");
            // The white W touches the white orbital gap in the source, so a
            // background flood fill alone would also erase this foreground letter.
            // This mask preserves the existing pixels; it does not redraw the W.
            letter.AddPolygon(new PointF[] {
                new PointF(165,131), new PointF(213,131), new PointF(239,193),
                new PointF(260,131), new PointF(293,131), new PointF(315,190),
                new PointF(334,131), new PointF(383,131), new PointF(342,266),
                new PointF(296,266), new PointF(275,211), new PointF(253,266),
                new PointF(207,266)
            });
            int transparent = 0, partial = 0;
            for (int y = 0; y < original.Height; y++) {
                for (int x = 0; x < original.Width; x++) {
                    Color pixel = original.GetPixel(x, y);
                    int min = Min(pixel);
                    if (letter.IsVisible(x, y) || min <= 60) {
                        output.SetPixel(x, y, Color.FromArgb(255, pixel.R, pixel.G, pixel.B));
                        continue;
                    }
                    if (min >= 245) { transparent++; continue; }
                    // Recover edge alpha and remove the original white matte
                    // instead of leaving a white fringe around blue lettering.
                    Color core = Color.Empty;
                    int distance = int.MaxValue;
                    for (int dy = -3; dy <= 3; dy++) for (int dx = -3; dx <= 3; dx++) {
                        int nx = x + dx, ny = y + dy, d = dx * dx + dy * dy;
                        if (nx < 0 || ny < 0 || nx >= original.Width || ny >= original.Height || d >= distance) continue;
                        Color candidate = original.GetPixel(nx, ny);
                        if (Min(candidate) <= 60) { core = candidate; distance = d; }
                    }
                    if (core.IsEmpty) { transparent++; continue; }
                    double r = 255 - core.R, g = 255 - core.G, b = 255 - core.B;
                    double alpha = Math.Max(0, Math.Min(1,
                        ((255 - pixel.R) * r + (255 - pixel.G) * g + (255 - pixel.B) * b) / (r*r + g*g + b*b)));
                    if (alpha < 0.04) { transparent++; continue; }
                    output.SetPixel(x, y, Color.FromArgb(Clamp(alpha * 255),
                        Clamp(255 + (pixel.R - 255) / alpha),
                        Clamp(255 + (pixel.G - 255) / alpha),
                        Clamp(255 + (pixel.B - 255) / alpha)));
                    partial++;
                }
            }
            output.Save(destination, ImageFormat.Png);
            Console.WriteLine("Transparent pixels: {0}; feathered edge pixels: {1}", transparent, partial);
        }
    }
}
'@
$logoSource = Join-Path $PSScriptRoot '../public/witw_logo.png'
$logoTarget = Join-Path $PSScriptRoot '../public/witw_logo_transparent.png'
[HeaderLogoMatte]::Convert($logoSource, $logoTarget)
