# DataPreParser Current Documentation

This document describes the current working state of `DataPreParser`: project structure, runtime folder setup, configuration files, task/wrapper behavior, marker parsing, device parsing, hooks, file masks, and output generation.

The project is still a refactor/migration of older parser logic. Some behavior intentionally follows legacy semantics even where a stricter new implementation might normally be preferred.

## Command Line Usage

Run the parser with:

```powershell
dotnet run --project DataPreParser\DataPreParser.csproj -- parse --input <subjectFolder>
```

Run multiple subjects from one parent folder with:

```powershell
dotnet run --project DataPreParser\DataPreParser.csproj -- parse --input-batch <subjectsRootFolder>
```

For a built executable:

```powershell
DataPreParser parse --input <subjectFolder>
DataPreParser parse --input-batch <subjectsRootFolder>
```

The `--input` path is a subject folder. It is not the config folder.

The `--input-batch` path is a parent folder containing multiple direct subject folders. Each direct subfolder is parsed as one subject.

Example:

```powershell
DataPreParser parse --input C:\Users\EyeQTrack\Downloads\subject1
```

Batch example:

```powershell
DataPreParser parse --input-batch C:\Users\EyeQTrack\Downloads\allSubjects
```

## Runtime Folder Structure

The executable loads config relative to the application base directory:

```text
AppFolder/
  DataPreParser.exe
  DataPreParser.dll
  config/
    main/
      DeviceInputs.xml
      MarkerInputs.xml
      Tasks.xml
      WrapperTasks.xml
  hooks/
    FileContentReadHook/
      OptionalHook.dll
    TimeOffsetHook/
      OptionalTimeHook.dll
```

In development, the source config lives here and is copied to the build output:

```text
DataPreParser/
  config/
    main/
      DeviceInputs.xml
      MarkerInputs.xml
      Tasks.xml
      WrapperTasks.xml
```

The project file copies `config\main\*.xml` to output on build.

## Complete Config Reference

This section is the compact reference for all currently supported XML config fields.

### Shared Input Attributes

These attributes can be used on both device input nodes and marker input nodes:

```text
prefix
suffix
extension
fileContentReadHookName
FileContentReadHookName
```

`prefix`, `suffix`, and `extension` define file matching.

`fileContentReadHookName` and `FileContentReadHookName` are equivalent. The value must match the hook DLL filename without `.dll`.

### Shared Input Elements

These elements can be used on both device input nodes and marker input nodes:

```text
SkipLastLines
TimeOffset
```

Defaults:

```text
SkipLastLines = 0
TimeOffset.useFixedTimeOffsetValue = true
TimeOffset.fixedTimeOffsetValue = 0
```

`SkipLastLines` removes trailing lines after file content is loaded and before parsing starts.

### Device Elements

Supported device-only elements:

```text
Delimiter
LineOfFirstData
ReplaceChar
ReplaceBy
UseFieldsIndex
FieldIndexOfTimestamp
Divider
DropIfCellIsEmpty
ColumnTitlesCustom
```

Defaults:

```text
Delimiter = ","
LineOfFirstData = 0
ReplaceChar = ""
ReplaceBy = ""
UseFieldsIndex = ""
FieldIndexOfTimestamp = 0
Divider = 1
DropIfCellIsEmpty = -1
ColumnTitlesCustom = ""
```

All device elements can be set in `DeviceInputs.xml` and overridden per task in `Tasks.xml`.

### Task Elements

Supported task-level elements:

```text
ExpectedSections
```

Defaults:

```text
ExpectedSections = -1
```

`ExpectedSections` validates the number of marker-based sections expected for this concrete task. The check is performed during device export, because that is where subselections are created, but the expected value belongs to the task rather than to the marker or device definition.

### Marker Elements

Required marker elements:

```text
ColumnDelimiter
LineOfFirstData
FieldIndexOfTimestamp
FieldIndexOfMarkers
MarkerNumbers
MarkerAliases
EndingMarkers
```

Optional marker elements:

```text
IgnoreMarkers
ReplaceMarkerBefore
ExpectedColumnCount
MinLineChars
Divider
SkipLastLines
TimeOffset
```

Defaults for optional marker elements:

```text
IgnoreMarkers = null
ReplaceMarkerBefore = null
ExpectedColumnCount = -1
MinLineChars = 0
Divider = 1
SkipLastLines = 0
```

Currently, task-level marker overrides support:

```text
prefix
suffix
extension
fileContentReadHookName
SkipLastLines
TimeOffset
```

Other marker parsing fields are read from `MarkerInputs.xml`.

### Legacy Field Mapping

Some old parser concepts map to newer config fields:

```text
ColumnDelimiter          -> Delimiter for devices, ColumnDelimiter for markers
TimeStampOffset          -> TimeOffset fixedTimeOffsetValue
CalculateAbsoluteTimestamp=false -> Divider 1, usually no epoch conversion
CalculateAbsoluteTimestamp=true  -> Divider 1000 if old timestamps are milliseconds
```

There is currently no separate `CalculateAbsoluteTimestamp` property in the new DTO. Timestamp normalization is done with:

```text
timestamp / Divider + TimeOffset
```

## Subject Input Folder Structure

The input folder represents one subject.

The parser expects direct child folders whose names match task-wrapper names.

Example:

```text
subject1/
  CAVIRGraz/
    markers_cavir.csv
```

For each matching wrapper/task folder, the parser scans:

```text
subject1/<WrapperTaskName>/
subject1/<WrapperTaskName>/**/*
```

The wrapper folder itself and all nested subfolders are treated as parsing folders. In each parsing folder, files are matched for the current task.

Example with nested structure:

```text
subject1/
  CAVIRGraz/
    Run01/
      markers_cavir.csv
    Run02/
      markers_cavir.csv
```

The parser processes `Run01` and `Run02` independently.

### Multiple Subjects

For multi-subject runs, use `--input-batch` with a parent folder:

```text
allSubjects/
  subject1/
    CAVIRGraz/
      markers_cavir.csv
  subject2/
    CAVIRGraz/
      markers_cavir.csv
```

Command:

```powershell
DataPreParser parse --input-batch C:\path\to\allSubjects
```

The parser processes each direct subfolder of `allSubjects` as an independent subject. Output is written into each subject's own `output` folder:

```text
allSubjects/
  subject1/
    output/
      *_preparsed.csv
  subject2/
    output/
      *_preparsed.csv
```

## Config Overview

All config files use:

```xml
<Config>
  ...
</Config>
```

The current config files are:

```text
DeviceInputs.xml
MarkerInputs.xml
Tasks.xml
WrapperTasks.xml
```

High-level meaning:

```text
DeviceInputs.xml
  Global/default device data file definitions.

MarkerInputs.xml
  Global/default marker/event file definitions.

Tasks.xml
  Concrete parsing tasks.
  Tasks select marker inputs and can override defaults.

WrapperTasks.xml
  Optional grouping of tasks under wrapper names.
```

## Current Processing Flow

For one `parse` command:

1. Load hooks from `hooks`.
2. Load all XML config from `config\main`.
3. Build one `ParserConfigData` object.
4. Resolve task definitions from defaults plus task overrides.
5. Resolve wrapper task definitions.
6. For each wrapper folder found in the subject folder:
   - scan the wrapper folder and all nested subfolders
   - for each task in the wrapper:
     - find all required marker files
     - parse markers into a sorted marker dictionary
     - find matching device files
     - parse each device that matched exactly one file
     - cut device data into marker subselections
     - write output CSV files

### Marker and Device Matching Rules

Marker files and device files are intentionally handled differently.

Markers are required at task/folder level. If any marker input configured for the current task does not find exactly one matching file in the current parsing folder, the whole task/folder is skipped. This is necessary because device parsing depends on the sorted marker timeline.

Devices are handled independently. If a configured, non-ignored device input does not find exactly one matching file, only that device is skipped. Other matching devices for the same task/folder can still be parsed against the already parsed marker timeline.

## ParserConfigData

The loaded config object contains:

```csharp
Dictionary<string, DeviceInputFileDetails> DeviceInputInformation
Dictionary<string, MarkerInputFileDetails> MarkerInputInformation
Dictionary<string, TaskDefinition> TaskDefinitions
Dictionary<string, string[]> WrapperTaskDefinitions
```

`DeviceInputInformation` and `MarkerInputInformation` are global reference/default dictionaries.

`TaskDefinitions` contains already resolved per-task config, including overrides.

`WrapperTaskDefinitions` maps wrapper names to task names.

## File Matching

Both marker and device files use the same file matching function.

Configured fields:

```xml
prefix=".*"
suffix="markers_(?:cavir|rc).*"
extension="csv"
```

The current matcher builds:

```csharp
pattern = prefix + suffix + ".*";
```

and searches by extension:

```text
extension="csv" -> *.csv
extension="txt" -> *.txt
extension="*"   -> *.*
```

Then it applies:

```csharp
Regex.IsMatch(Path.GetFileName(file), pattern)
```

Important: `prefix` and `suffix` are regex-capable. They are not escaped.

Example:

```xml
prefix=".*"
suffix="markers_(?:cavir|rc).*"
extension="csv"
```

matches:

```text
markers_cavir.csv
markers_rc.csv
some_prefix_markers_cavir_anything.csv
```

Expected file count is currently fixed at `1`.

Marker matching is task-level required: if any configured marker input for a task does not find exactly one file in a parsing folder, that task/folder is skipped.

Device matching is device-level optional: if a configured device input does not find exactly one file, only that device is skipped. Other matching devices in the same task/folder can still be parsed.

## DeviceInputs.xml

`DeviceInputs.xml` defines global/default device data file configs.

Each first-level node below `Config` is a device input. The node name is the device name and dictionary key.

Example:

```xml
<Config>
  <EyetrackingHeadset prefix=".*" suffix="markers_(?:cavir|rc).*" extension="csv">
    <Delimiter>;</Delimiter>
    <LineOfFirstData>0</LineOfFirstData>
    <ReplaceChar></ReplaceChar>
    <ReplaceBy></ReplaceBy>
    <UseFieldsIndex>3,4,5,6,7,8,9,10,11,12,13,14,15,16</UseFieldsIndex>
    <FieldIndexOfTimestamp>0</FieldIndexOfTimestamp>
    <Divider>1</Divider>
    <DropIfCellIsEmpty>0</DropIfCellIsEmpty>
    <TimeOffset fixedTimeOffsetValue="0" useFixedTimeOffsetValue="true" />
  </EyetrackingHeadset>
</Config>
```

Supported attributes:

```text
prefix
suffix
extension
fileContentReadHookName
FileContentReadHookName
```

Supported child elements:

```text
Delimiter
LineOfFirstData
SkipLastLines
ReplaceChar
ReplaceBy
UseFieldsIndex
FieldIndexOfTimestamp
Divider
DropIfCellIsEmpty
ColumnTitlesCustom
TimeOffset
```

### Device Property Meaning

`Delimiter`
: Field delimiter. The special value `tab` becomes `\t`.

`LineOfFirstData`
: Header/data skip setting. Current device parser skips while `lineNumber <= LineOfFirstData`.

`SkipLastLines`
: Number of trailing lines to remove before parsing. Default is `0`.

`ReplaceChar` and `ReplaceBy`
: Optional replacement applied to selected output values.

`UseFieldsIndex`
: Comma-separated list of source field indices to export. If empty, all fields are exported.

`FieldIndexOfTimestamp`
: Source field index used as the data timestamp.

`Divider`
: Timestamp divider. Default is `1`. Example: `1000` converts milliseconds to seconds.

`DropIfCellIsEmpty`
: If not `-1`, rows are skipped when the configured field index is empty.

`ColumnTitlesCustom`
: Optional header line written to output files.

`TimeOffset`
: Shared time offset configuration.

## MarkerInputs.xml

`MarkerInputs.xml` defines global/default marker file configs.

Example:

```xml
<Config>
  <RedCross_Cavir_HMD_Markers prefix=".*" suffix="markers_(?:cavir|rc).*" extension="csv">
    <ColumnDelimiter>;</ColumnDelimiter>
    <LineOfFirstData>0</LineOfFirstData>
    <FieldIndexOfTimestamp>0</FieldIndexOfTimestamp>
    <FieldIndexOfMarkers>2</FieldIndexOfMarkers>
    <MarkerNumbers>scene1_work,scene2_work,scene3_work,scene4_work,scene5_work,RedCross_1_running</MarkerNumbers>
    <MarkerAliases>Start1,Start2,Start3,Start4,Start5,RedCross</MarkerAliases>
    <EndingMarkers>scene1_end,scene2_end,scene3_end,scene4_end,scene5_end</EndingMarkers>
    <IgnoreMarkers>scene1_intro,scene2_intro,scene3_intro,scene4_intro,scene5_intro,starting_phase,wait_for_closing</IgnoreMarkers>
    <ReplaceMarkerBefore>scene5_end,scene5_work,245</ReplaceMarkerBefore>
  </RedCross_Cavir_HMD_Markers>
</Config>
```

Supported attributes:

```text
prefix
suffix
extension
fileContentReadHookName
FileContentReadHookName
```

Required marker elements:

```text
ColumnDelimiter
LineOfFirstData
FieldIndexOfTimestamp
FieldIndexOfMarkers
MarkerNumbers
MarkerAliases
EndingMarkers
```

Optional marker elements:

```text
IgnoreMarkers
ReplaceMarkerBefore
ExpectedColumnCount
MinLineChars
SkipLastLines
Divider
TimeOffset
```

### MarkerNumbers and MarkerAliases

`MarkerNumbers` and `MarkerAliases` are positional mappings.

Example:

```xml
<MarkerNumbers>scene1_work,scene2_work</MarkerNumbers>
<MarkerAliases>Start1,Start2</MarkerAliases>
```

means:

```text
scene1_work -> Start1
scene2_work -> Start2
```

They are not filters. A marker value not listed in `MarkerNumbers` can still be emitted with its raw value unless filtered elsewhere.

### IgnoreMarkers

`IgnoreMarkers` is the main explicit marker exclusion list.

Example:

```xml
<IgnoreMarkers>starting_phase,wait_for_closing</IgnoreMarkers>
```

Those raw marker values are skipped.

The parser also has a hardcoded skip for marker value `"0"`.

### EndingMarkers

`EndingMarkers` defines raw marker values that are treated as end markers.

Example:

```xml
<EndingMarkers>scene1_end,scene2_end</EndingMarkers>
```

These values must match raw values in the marker file, not aliases.

If an expected ending marker is missing, the parser may insert manual end markers:

```text
_manualEnd
_manualFinalEnd
```

If an ending marker appears while no start marker is open, it is usually skipped unless `ReplaceMarkerBefore` has provided a replacement start.

### ReplaceMarkerBefore

`ReplaceMarkerBefore` has the shape:

```text
endingMarker,startMarker,secondsBeforeEnd
```

Example:

```xml
<ReplaceMarkerBefore>scene5_end,scene5_work,245</ReplaceMarkerBefore>
```

When the parser encounters `scene5_end`, it can add a synthetic `scene5_work` start marker at:

```text
scene5_end_timestamp - 245
```

Do not use marker aliases here. Use raw marker values.

### SkipLastLines

Markers support the shared `SkipLastLines` element:

```xml
<SkipLastLines>1</SkipLastLines>
```

The parser removes that many trailing lines from the loaded marker file content before applying marker parsing logic. Default is `0`.

## TimeOffset

`TimeOffset` can be configured on both marker inputs and device inputs.

Example fixed offset:

```xml
<TimeOffset fixedTimeOffsetValue="0" useFixedTimeOffsetValue="true" />
```

Example hook-based offset:

```xml
<TimeOffset
  filePrefix=".*"
  filePostfix="epoch.*"
  fileExtension="txt"
  timeOffsetHookName="MyTimeOffsetHook"
  fixedTimeOffsetValue="0"
  useFixedTimeOffsetValue="false" />
```

Defaults:

```text
filePrefix = ""
filePostfix = ""
fileExtension = ""
timeOffsetHookName = ""
fixedTimeOffsetValue = 0
useFixedTimeOffsetValue = true
```

Runtime behavior:

```text
useFixedTimeOffsetValue = true
  -> use fixedTimeOffsetValue

useFixedTimeOffsetValue = false
  -> find offset file next to the source file
  -> look up ITimeOffsetHook by timeOffsetHookName
  -> call GetTimeOffset(filePath)
```

The returned offset is a `double` in seconds.

## Tasks.xml

`Tasks.xml` defines concrete tasks.

Current example:

```xml
<Config>
  <CAVIRGraz>
    <ExpectedSections>6</ExpectedSections>
    <DeviceInputs>
    </DeviceInputs>
    <MarkerInputs>
      <RedCross_Cavir_HMD_Markers />
    </MarkerInputs>
  </CAVIRGraz>
</Config>
```

### Device Task Behavior

Devices are included by default.

For each task, the parser starts by copying all entries from `DeviceInputs.xml`.

A task can then:

1. Ignore devices.
2. Override device attributes/elements.

Ignore example:

```xml
<EEGEmotiv ignoreDeviceInputForThisTask="true" />
```

Override example:

```xml
<EyetrackingHeadset suffix="markers_(?:cavir|rc).*">
  <FieldIndexOfTimestamp>0</FieldIndexOfTimestamp>
  <Divider>1</Divider>
</EyetrackingHeadset>
```

Missing override fields inherit from `DeviceInputs.xml`.

### Marker Task Behavior

Markers are not included by default.

A task gets only marker inputs that are explicitly listed.

Example:

```xml
<MarkerInputs>
  <RedCross_Cavir_HMD_Markers />
</MarkerInputs>
```

Task-level marker overrides currently support:

```text
prefix
suffix
extension
fileContentReadHookName
SkipLastLines
TimeOffset
```

The rest of marker parsing config currently comes from `MarkerInputs.xml`.

## WrapperTasks.xml

`WrapperTasks.xml` optionally groups tasks under a folder name.

Example:

```xml
<Config>
  <FullExperiment>
    <CAVIRGraz />
    <AnotherTask />
  </FullExperiment>
</Config>
```

Then the expected subject folder is:

```text
subject1/
  FullExperiment/
    ...
```

If `WrapperTasks.xml` is empty:

```xml
<Config>

</Config>
```

then every task not listed in a wrapper automatically receives a one-task wrapper with the same name.

For the current `CAVIRGraz` task, an empty `WrapperTasks.xml` means:

```text
WrapperTaskDefinitions["CAVIRGraz"] = ["CAVIRGraz"]
```

Expected folder:

```text
subject1/
  CAVIRGraz/
    markers_cavir.csv
```

`WrapperTasks.xml` currently does not support overrides. Overrides belong in `Tasks.xml`.

## Hooks

There are two hook types.

### FileContentReadHook

Interface:

```csharp
public interface IFileContentReadHook
{
    string GetPreparedFileContent(string filePath);
}
```

Runtime folder:

```text
AppFolder/
  hooks/
    FileContentReadHook/
      MyHook.dll
```

The hook key is the DLL filename without extension:

```text
MyHook.dll -> MyHook
```

Config usage:

```xml
<EyetrackingHeadset
  prefix=".*"
  suffix="markers_(?:cavir|rc).*"
  extension="csv"
  fileContentReadHookName="MyHook">
  ...
</EyetrackingHeadset>
```

If `fileContentReadHookName` is empty or missing, normal `File.ReadAllLines` is used.

### TimeOffsetHook

Interface:

```csharp
public interface ITimeOffsetHook
{
    double GetTimeOffset(string filePath);
}
```

Runtime folder:

```text
AppFolder/
  hooks/
    TimeOffsetHook/
      MyTimeOffsetHook.dll
```

Config usage:

```xml
<TimeOffset
  filePrefix=".*"
  filePostfix="offset.*"
  fileExtension="txt"
  timeOffsetHookName="MyTimeOffsetHook"
  useFixedTimeOffsetValue="false" />
```

## Marker Parsing Output

Marker parsing builds:

```csharp
SortedDictionary<double, string>
```

The key is the absolute marker timestamp.

The value is the marker name with suffix:

```text
_start
_end
```

Example:

```text
1738745800.123 -> Start1_start
1738745900.456 -> Start1_end
```

The marker dictionary is sorted by timestamp.

If two markers have exactly the same timestamp, the parser increments the timestamp by `0.000001` until it is unique.

## Device Parsing and Subsections

After markers are parsed, device data is parsed against the sorted marker dictionary.

The device parser:

1. Reads the device file.
2. Applies optional file-content hook.
3. Skips header/data lines.
4. Splits by delimiter.
5. Reads timestamp.
6. Applies divider and time offset.
7. Selects configured value fields.
8. Applies replacements.
9. Calls `MarkerFileParser.Subselections(...)`.
10. Validates `ExpectedSections` if configured.
11. Writes output files.

Subsections are built from marker intervals. The function looks at marker entries where a current marker is followed by a marker containing `_end`.

For each interval, it finds closest device timestamps to the marker start and end and copies all rows in that range.

`ExpectedSections` is configured on the task. If it is not `-1` and the number of subsections does not match, output for the current device is skipped and an error is printed.

## Output Folder and File Names

Output is written into:

```text
<subjectFolder>/output/
```

For example:

```text
subject1/
  output/
    CAVIRGraz_Start1_start1784226424948_EyetrackingHeadset_preparsed.csv
  CAVIRGraz/
    markers_cavir.csv
```

Output filename shape:

```text
{taskName}_{markerSubselectionKey}_{deviceInput.Name}_preparsed.csv
```

`markerSubselectionKey` currently includes:

```text
marker name + DateTimeOffset.Now.ToUnixTimeMilliseconds()
```

That means output file names are not deterministic between runs.

## Current CAVIRGraz Example

Current task:

```xml
<CAVIRGraz>
  <ExpectedSections>6</ExpectedSections>
  <DeviceInputs>
  </DeviceInputs>
  <MarkerInputs>
    <RedCross_Cavir_HMD_Markers />
  </MarkerInputs>
</CAVIRGraz>
```

Because devices are included by default, this task currently starts with all globally configured device inputs. Device files that are missing or ambiguous are skipped individually. With the current subject test data, `EyetrackingHeadset` is the matching device input because its file mask matches `markers_cavir.csv`.

Expected folder:

```text
subject1/
  CAVIRGraz/
    markers_cavir.csv
```

The same file is currently used both as:

```text
RedCross_Cavir_HMD_Markers
EyetrackingHeadset
```

This works because both file masks match `markers_cavir.csv`.

For this specific file, both marker parsing and device parsing must use compatible timestamp columns. Current working setup:

```xml
<RedCross_Cavir_HMD_Markers>
  <FieldIndexOfTimestamp>0</FieldIndexOfTimestamp>
</RedCross_Cavir_HMD_Markers>

<EyetrackingHeadset>
  <FieldIndexOfTimestamp>0</FieldIndexOfTimestamp>
  <Divider>1</Divider>
</EyetrackingHeadset>
```

If the device config used timestamp column `1`, device timestamps would be relative seconds while marker timestamps would be epoch seconds. Subsections would collapse to one-row outputs.

## Adding a New Task Variant

Use separate task definitions when file masks or parsing settings differ.

Example:

```xml
<Config>
  <CAVIRGraz_HMD>
    <DeviceInputs>
      <EEGEmotiv ignoreDeviceInputForThisTask="true" />
      <EyetrackingHeadset>
        <FieldIndexOfTimestamp>0</FieldIndexOfTimestamp>
        <Divider>1</Divider>
      </EyetrackingHeadset>
    </DeviceInputs>
    <MarkerInputs>
      <RedCross_Cavir_HMD_Markers />
    </MarkerInputs>
  </CAVIRGraz_HMD>

  <CAVIRGraz_Keyboard>
    <DeviceInputs>
      <EyetrackingHeadset ignoreDeviceInputForThisTask="true" />
    </DeviceInputs>
    <MarkerInputs>
      <KeyBoardToolMarkers />
    </MarkerInputs>
  </CAVIRGraz_Keyboard>
</Config>
```

Group them with a wrapper:

```xml
<Config>
  <CAVIRGraz>
    <CAVIRGraz_HMD />
    <CAVIRGraz_Keyboard />
  </CAVIRGraz>
</Config>
```

Expected folder:

```text
subject1/
  CAVIRGraz/
    ...
```

## Common Failure Modes

No parsing happens:

```text
The subject folder probably does not contain a direct child folder matching a wrapper/task name.
```

Marker parsing works but device parsing does not:

```text
The device file may be missing, matched more than one file, or failed during device data parsing.
Missing or overmatching devices are skipped individually.
```

Only one output row per subsection:

```text
Marker timestamps and device timestamps are probably on different timelines.
Check FieldIndexOfTimestamp, Divider, and TimeOffset for both marker and device input.
```

Config reference is ignored:

```text
A task references a device or marker name that does not exist in the corresponding reference XML.
Current behavior is to skip unknown references silently.
```

Hook not found:

```text
The configured hook name must match the DLL filename without .dll.
```

Multiple matching files:

```text
Expected file count is currently fixed at 1.
For markers, this skips the task/folder.
For devices, this skips only that device.
Make prefix/suffix/extension more specific or split variants into separate tasks.
```

## Current Limitations

- Expected file count is fixed at `1`.
- Unknown config references are skipped silently.
- `WrapperTasks.xml` cannot override task config.
- Output CSV values are written with simple comma joining, without full CSV escaping.
- Output file names include current Unix milliseconds and are therefore nondeterministic.
- `DeviceInputs` and `MarkerInputs` in `TaskDefinition` are arrays, not dictionaries.
- The parser currently catches missing file matches by skipping the task/folder, not by reporting detailed warnings.
- The namespace is still historically `ConsoleApp4`.

## Useful Commands

Build:

```powershell
dotnet build DataPreParser\DataPreParser.csproj
```

Run current subject example:

```powershell
dotnet run --project DataPreParser\DataPreParser.csproj -- parse --input C:\Users\EyeQTrack\Downloads\subject1
```

Run multiple subjects:

```powershell
dotnet run --project DataPreParser\DataPreParser.csproj -- parse --input-batch C:\Users\EyeQTrack\Downloads\allSubjects
```

Check generated output:

```powershell
Get-ChildItem C:\Users\EyeQTrack\Downloads\subject1\output
```
