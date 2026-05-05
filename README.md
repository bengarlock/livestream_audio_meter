# Livestream Audio Meter

Realtime audio level meter for an RTSP/RTSPS livestream.

The script uses FFmpeg to decode the stream audio into raw PCM, then reports:

- RMS level in dBFS
- Peak level in dBFS
- Running average RMS level
- Loudness label: `Very Loud`, `Loud`, `Moderate`, or `Quiet`

`dBFS` means decibels relative to full scale. It is the normal unit for digital audio level measurement. Physical loudness in dB SPL requires calibrated capture hardware and a known reference.

Default loudness labels are based on RMS dBFS:

- `Very Loud`: `-12 dBFS` and above
- `Loud`: `-24 dBFS` to below `-12 dBFS`
- `Moderate`: `-40 dBFS` to below `-24 dBFS`
- `Quiet`: below `-40 dBFS`

## Requirements

- Python 3.10+
- FFmpeg installed and available on `PATH`

## Install FFmpeg

### Windows

Recommended option with Winget:

```powershell
winget install Gyan.FFmpeg
```

Close and reopen PowerShell or PyCharm after installation, then check:

```powershell
ffmpeg -version
```

Alternative option with Chocolatey:

```powershell
choco install ffmpeg
```

If `ffmpeg -version` is not recognized after installing, make sure the FFmpeg `bin` folder is on your Windows `PATH`, then restart your terminal.

### macOS

Recommended option with Homebrew:

```bash
brew install ffmpeg
```

Check the installation:

```bash
ffmpeg -version
```

If Homebrew is not installed, install it from <https://brew.sh/>, restart your terminal, then run the `brew install ffmpeg` command above.

## Run

```powershell
cd C:\Users\benga\PycharmProjects\livestream_audio_meter
python .\audio_meter.py "rtsps://192.168.1.1:7441/ufgIVAE3C4ZeCNQy?enableSrtp"
```

If the stream works better over UDP than TCP, run:

```powershell
python .\audio_meter.py "rtsps://192.168.1.1:7441/ufgIVAE3C4ZeCNQy?enableSrtp" --rtsp-transport udp
```

For machine-readable output:

```powershell
python .\audio_meter.py "rtsps://192.168.1.1:7441/ufgIVAE3C4ZeCNQy?enableSrtp" --json
```

Stop with `Ctrl+C`.
