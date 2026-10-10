# GTB3000 창 캡처 (개발용): 스타일별로 실행 → 창만 PrintWindow 로 캡처 → 종료
param([string[]]$Styles = @("native", "classic", "flat", "dark"), [string]$Out = "$PSScriptRoot\..\shots", [int]$Tab = 0)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
  public struct RECT { public int L, T, R, B; }
}
"@
New-Item -ItemType Directory -Force $Out | Out-Null
$exe = Resolve-Path "$PSScriptRoot\..\dist\GTB3000.exe"
foreach ($s in $Styles) {
  $p = Start-Process $exe -ArgumentList "/user=operator", "/style=$s", "/seed=1", "/tab=$Tab" -PassThru
  $h = [IntPtr]::Zero
  for ($i = 0; $i -lt 40 -and $h -eq [IntPtr]::Zero; $i++) { Start-Sleep -Milliseconds 250; $p.Refresh(); $h = $p.MainWindowHandle }
  Start-Sleep -Milliseconds 1200
  $r = New-Object W+RECT
  [W]::GetWindowRect($h, [ref]$r) | Out-Null
  $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $hdc = $g.GetHdc(); [W]::PrintWindow($h, $hdc, 2) | Out-Null; $g.ReleaseHdc($hdc); $g.Dispose()
  $bmp.Save("$Out\gtb_${s}_tab$Tab.png"); $bmp.Dispose()
  Stop-Process -Id $p.Id -Force
  "saved gtb_${s}_tab$Tab.png ($($r.R - $r.L)x$($r.B - $r.T))"
}
