# DataPreParser

Cuts the raw recordings of a CAVIR session into task segments and aligns all device streams to Unix
time. It produces the `02_PREPARSED` level of the CAVIR dataset from `01_RAW`.

- `DataPreParser/`: the parser (C#, .NET 8)
- `CavirTimeOffset/`: the time-offset hook. It converts the iMotions timestamps, which are relative to
  the start of the recording, to Unix time using the recording start in `Native_SlideEvents.csv`.
- `config/2025_USTP/`, `config/2026_USTP/`: the configuration used for each data-collection period
- `docs/`: detailed documentation of the configuration files, hooks and output

## Requirements

[.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)

## Build

```
dotnet build DataPreParser/DataPreParser.csproj -c Release
dotnet build CavirTimeOffset/CavirTimeOffset.csproj -c Release
```

## Set up the runtime folder

The parser reads its configuration from `config/main/` and the hooks from `hooks/` next to the
executable (`DataPreParser/bin/Release/net8.0/`):

```
net8.0/
├── DataPreParser.exe
├── config/main/              the four XML files of the period to parse
│                             (from config/2025_USTP/ or config/2026_USTP/)
└── hooks/TimeOffsetHook/
    └── CavirTimeOffset.dll   (from CavirTimeOffset/bin/Release/net8.0/)
```

## Run

The `--input` folder is one participant folder. It must contain a subfolder named after the task in
`Tasks.xml` (`CAVIR`), which holds the raw files. This is the structure of `01_RAW`:

```
<participant_id>/            <- --input
└── CAVIR/
    ├── *_markers_cavir.csv
    ├── HeartRate_Polar*_ET_Ble_BleSensor.csv
    ├── Native_SlideEvents.csv
    └── ...
```

One participant:

```
DataPreParser parse --input 01_RAW/2026_USTP/<participant_id>
```

All participants of one period (each direct subfolder is parsed as one participant):

```
DataPreParser parse --input-batch 01_RAW/2026_USTP
```

The preparsed files are written to `<participant_id>/output/*_preparsed.csv`. File names contain a
`start<timestamp>` part that is set at parsing time and differs between runs; the file contents do
not.

## Configuration

The four XML files in `config/main/`:

```
DeviceInputs.xml   device data files (eye tracking, Polar, EEG, GSR): file pattern, columns,
                   time format and time offset
MarkerInputs.xml   marker files (task markers in the headset log)
Tasks.xml          tasks (here: CAVIR), the marker input used and the expected number of sections
WrapperTasks.xml   optional grouping of tasks (empty for CAVIR)
```

Files are found by regex patterns, for example:

```xml
prefix=".*" suffix="markers_(?:cavir|rc).*" extension="csv"
```

- If the marker file of a task is missing or ambiguous, the participant is skipped for that task.
- Device files are handled independently: a missing or ambiguous device file only skips that
  device.
- `ExpectedSections` in `Tasks.xml` checks the number of marker sections. If it does not match,
  the export of that device is skipped and an error is printed.

The full documentation covers config inheritance, task overrides, wrapper tasks, hooks, time
offsets, marker and device parsing, output files and common failure modes:
[docs/DataPreParser_Current_Documentation.md](docs/DataPreParser_Current_Documentation.md)
(also as PDF and HTML).

Besides eye tracking and heart rate, the parser also writes EEG and GSR segments. These are not part
of `02_PREPARSED` in the released dataset (see the dataset README).

## Provenance

The CAVIR dataset was preparsed with a build of commit `e6cd77f` ("Implement hooks", 27 July 2026)
of the internal DataPreParser repository, using the same binary for both periods. The periods differ
only in their configuration:

- `Tasks.xml`: number of expected marker sections (6 in 2025, 11 in 2026, which additionally logged
  the EEG baseline and the eye-tracking calibration)
- `DeviceInputs.xml`: file name of the Polar export

Rebuilding this code and parsing one participant of each period reproduced the released preparsed
files byte for byte.
