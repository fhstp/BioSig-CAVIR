using System.Globalization;
using System.Xml.Linq;

namespace ConsoleApp4;

internal static class ParserConfigReader
{
    private const string ConfigRootName = "Config";
    private const string TasksFileName = "Tasks";
    private const string WrapperTasksFileName = "WrapperTasks";
    private const string DeviceInputsFileName = "DeviceInputs";
    private const string MarkerInputsFileName = "MarkerInputs";
    private const string DeviceInputsNodeName = "DeviceInputs";
    private const string MarkerInputsNodeName = "MarkerInputs";

    public static ParserConfigData Load(string folderPath)
    {
        var tasksDocument = LoadDocument(folderPath, TasksFileName);
        var wrapperTasksDocument = LoadDocument(folderPath, WrapperTasksFileName);
        var deviceInputsDocument = LoadDocument(folderPath, DeviceInputsFileName);
        var markerInputsDocument = LoadDocument(folderPath, MarkerInputsFileName);

        var config = new ParserConfigData();

        ReadDeviceInputs(deviceInputsDocument, config.DeviceInputInformation);
        ReadMarkerInputs(markerInputsDocument, config.MarkerInputInformation);
        ReadTasks(
            tasksDocument,
            config.DeviceInputInformation,
            config.MarkerInputInformation,
            config.TaskDefinitions);
        ReadWrapperTasks(
            wrapperTasksDocument,
            config.TaskDefinitions,
            config.WrapperTaskDefinitions);

        return config;
    }

    private static void ReadDeviceInputs(
        XDocument document,
        Dictionary<string, DeviceInputFileDetails> deviceInputInformation)
    {
        foreach (var node in GetConfigRoot(document).Elements())
        {
            var name = node.Name.LocalName;

            deviceInputInformation[name] = new DeviceInputFileDetails
            {
                Name = name,
                Prefix = ReadAttribute(node, "prefix"),
                Suffix = ReadAttribute(node, "suffix"),
                Extension = ReadAttribute(node, "extension"),
                FileContentReadHookName = ReadFileContentReadHookName(node),
                SkipLastLines = ReadOptionalIntElementValue(node, "SkipLastLines", 0),
                Delimiter = ReadOptionalElementValue(node, "Delimiter", ","),
                LineOfFirstData = ReadOptionalIntElementValue(node, "LineOfFirstData", 0),
                ReplaceChar = ReadOptionalElementValue(node, "ReplaceChar", string.Empty),
                ReplaceBy = ReadOptionalElementValue(node, "ReplaceBy", string.Empty),
                UseFieldsIndex = ReadOptionalElementValue(node, "UseFieldsIndex", string.Empty),
                FieldIndexOfTimestamp = ReadOptionalIntElementValue(node, "FieldIndexOfTimestamp", 0),
                Divider = ReadOptionalIntElementValue(node, "Divider", 1),
                DropIfCellIsEmpty = ReadOptionalIntElementValue(node, "DropIfCellIsEmpty", -1),
                ColumnTitlesCustom = ReadOptionalElementValue(node, "ColumnTitlesCustom", string.Empty),
                TimeOffset = ReadTimeOffsetConfiguration(node)
            };
        }
    }

    private static void ReadMarkerInputs(
        XDocument document,
        Dictionary<string, MarkerInputFileDetails> markerInputInformation)
    {
        foreach (var node in GetConfigRoot(document).Elements())
        {
            var name = node.Name.LocalName;

            markerInputInformation[name] = new MarkerInputFileDetails
            {
                Name = name,
                Prefix = ReadAttribute(node, "prefix"),
                Suffix = ReadAttribute(node, "suffix"),
                Extension = ReadAttribute(node, "extension"),
                ColumnDelimiter = ReadRequiredElementValue(node, "ColumnDelimiter"),
                LineOfFirstData = ReadRequiredIntElementValue(node, "LineOfFirstData"),
                FieldIndexOfTimestamp = ReadRequiredIntElementValue(node, "FieldIndexOfTimestamp"),
                FieldIndexOfMarkers = ReadRequiredIntElementValue(node, "FieldIndexOfMarkers"),
                MarkerNumbers = ReadRequiredStringArrayElementValue(node, "MarkerNumbers"),
                MarkerAliases = ReadRequiredStringArrayElementValue(node, "MarkerAliases"),
                EndingMarkers = ReadRequiredStringArrayElementValue(node, "EndingMarkers"),
                IgnoreMarkers = ReadOptionalStringArrayElementValue(node, "IgnoreMarkers"),
                ReplaceMarkerBefore = ReadOptionalStringArrayElementValue(node, "ReplaceMarkerBefore"),
                FileContentReadHookName = ReadFileContentReadHookName(node),
                SkipLastLines = ReadOptionalIntElementValue(node, "SkipLastLines", 0),
                ExpectedColumnCount = ReadOptionalIntElementValue(node, "ExpectedColumnCount", -1),
                MinLineChars = ReadOptionalIntElementValue(node, "MinLineChars", 0),
                Divider = ReadOptionalIntElementValue(node, "Divider", 1),
                TimeOffset = ReadTimeOffsetConfiguration(node)
            };
        }
    }

    private static void ReadTasks(
        XDocument document,
        Dictionary<string, DeviceInputFileDetails> deviceInputInformation,
        Dictionary<string, MarkerInputFileDetails> markerInputInformation,
        Dictionary<string, TaskDefinition> taskDefinitions)
    {
        foreach (var taskNode in GetConfigRoot(document).Elements())
        {
            var taskName = taskNode.Name.LocalName;
            var deviceInputsForTask = CopyAllDeviceInputInformation(deviceInputInformation);
            var deviceInputsNode = taskNode.Elements()
                .SingleOrDefault(node => string.Equals(node.Name.LocalName, DeviceInputsNodeName, StringComparison.OrdinalIgnoreCase));

            if (deviceInputsNode is not null)
            {
                ApplyDeviceInputOverrides(deviceInputsNode, deviceInputInformation, deviceInputsForTask);
            }

            var markerInputsForTask = new List<MarkerInputFileDetails>();
            var markerInputsNode = taskNode.Elements()
                .SingleOrDefault(node => string.Equals(node.Name.LocalName, MarkerInputsNodeName, StringComparison.OrdinalIgnoreCase));

            if (markerInputsNode is not null)
            {
                ReadMarkerInputsForTask(markerInputsNode, markerInputInformation, markerInputsForTask);
            }

            taskDefinitions[taskName] = new TaskDefinition
            {
                Name = taskName,
                ExpectedSections = ReadOptionalIntElementValue(taskNode, "ExpectedSections", -1),
                DeviceInputs = deviceInputsForTask.Values.ToArray(),
                MarkerInputs = markerInputsForTask.ToArray()
            };
        }
    }

    private static void ApplyDeviceInputOverrides(
        XElement deviceInputsNode,
        Dictionary<string, DeviceInputFileDetails> deviceInputInformation,
        Dictionary<string, DeviceInputFileDetails> deviceInputsForTask)
    {
        foreach (var taskDeviceInputNode in deviceInputsNode.Elements())
        {
            var deviceInputName = taskDeviceInputNode.Name.LocalName;

            if (!deviceInputInformation.TryGetValue(deviceInputName, out var referenceDetails))
            {
                continue;
            }

            if (ReadBoolAttribute(taskDeviceInputNode, "ignoreDeviceInputForThisTask"))
            {
                deviceInputsForTask.Remove(deviceInputName);
                continue;
            }

            deviceInputsForTask[deviceInputName] = new DeviceInputFileDetails
            {
                Name = deviceInputName,
                Prefix = ReadOptionalAttribute(taskDeviceInputNode, "prefix") ?? referenceDetails.Prefix,
                Suffix = ReadOptionalAttribute(taskDeviceInputNode, "suffix") ?? referenceDetails.Suffix,
                Extension = ReadOptionalAttribute(taskDeviceInputNode, "extension") ?? referenceDetails.Extension,
                FileContentReadHookName = ReadFileContentReadHookName(taskDeviceInputNode, referenceDetails.FileContentReadHookName),
                SkipLastLines = ReadOptionalIntElementValue(taskDeviceInputNode, "SkipLastLines", referenceDetails.SkipLastLines),
                Delimiter = ReadOptionalElementValue(taskDeviceInputNode, "Delimiter", referenceDetails.Delimiter),
                LineOfFirstData = ReadOptionalIntElementValue(taskDeviceInputNode, "LineOfFirstData", referenceDetails.LineOfFirstData),
                ReplaceChar = ReadOptionalElementValue(taskDeviceInputNode, "ReplaceChar", referenceDetails.ReplaceChar),
                ReplaceBy = ReadOptionalElementValue(taskDeviceInputNode, "ReplaceBy", referenceDetails.ReplaceBy),
                UseFieldsIndex = ReadOptionalElementValue(taskDeviceInputNode, "UseFieldsIndex", referenceDetails.UseFieldsIndex),
                FieldIndexOfTimestamp = ReadOptionalIntElementValue(
                    taskDeviceInputNode,
                    "FieldIndexOfTimestamp",
                    referenceDetails.FieldIndexOfTimestamp),
                Divider = ReadOptionalIntElementValue(taskDeviceInputNode, "Divider", referenceDetails.Divider),
                DropIfCellIsEmpty = ReadOptionalIntElementValue(
                    taskDeviceInputNode,
                    "DropIfCellIsEmpty",
                    referenceDetails.DropIfCellIsEmpty),
                ColumnTitlesCustom = ReadOptionalElementValue(
                    taskDeviceInputNode,
                    "ColumnTitlesCustom",
                    referenceDetails.ColumnTitlesCustom),
                TimeOffset = ReadTimeOffsetConfigurationOverride(taskDeviceInputNode, referenceDetails.TimeOffset)
            };
        }
    }

    private static void ReadMarkerInputsForTask(
        XElement markerInputsNode,
        Dictionary<string, MarkerInputFileDetails> markerInputInformation,
        List<MarkerInputFileDetails> markerInputsForTask)
    {
        foreach (var taskMarkerInputNode in markerInputsNode.Elements())
        {
            var markerInputName = taskMarkerInputNode.Name.LocalName;

            if (!markerInputInformation.TryGetValue(markerInputName, out var referenceDetails))
            {
                continue;
            }

            markerInputsForTask.Add(new MarkerInputFileDetails
            {
                Name = markerInputName,
                Prefix = ReadOptionalAttribute(taskMarkerInputNode, "prefix") ?? referenceDetails.Prefix,
                Suffix = ReadOptionalAttribute(taskMarkerInputNode, "suffix") ?? referenceDetails.Suffix,
                Extension = ReadOptionalAttribute(taskMarkerInputNode, "extension") ?? referenceDetails.Extension,
                ColumnDelimiter = referenceDetails.ColumnDelimiter,
                LineOfFirstData = referenceDetails.LineOfFirstData,
                FieldIndexOfTimestamp = referenceDetails.FieldIndexOfTimestamp,
                FieldIndexOfMarkers = referenceDetails.FieldIndexOfMarkers,
                MarkerNumbers = referenceDetails.MarkerNumbers.ToArray(),
                MarkerAliases = referenceDetails.MarkerAliases.ToArray(),
                EndingMarkers = referenceDetails.EndingMarkers.ToArray(),
                IgnoreMarkers = referenceDetails.IgnoreMarkers?.ToArray(),
                ReplaceMarkerBefore = referenceDetails.ReplaceMarkerBefore?.ToArray(),
                FileContentReadHookName = ReadFileContentReadHookName(taskMarkerInputNode, referenceDetails.FileContentReadHookName),
                SkipLastLines = ReadOptionalIntElementValue(taskMarkerInputNode, "SkipLastLines", referenceDetails.SkipLastLines),
                ExpectedColumnCount = referenceDetails.ExpectedColumnCount,
                MinLineChars = referenceDetails.MinLineChars,
                Divider = referenceDetails.Divider,
                TimeOffset = ReadTimeOffsetConfigurationOverride(taskMarkerInputNode, referenceDetails.TimeOffset)
            });
        }
    }

    private static void ReadWrapperTasks(
        XDocument document,
        Dictionary<string, TaskDefinition> taskDefinitions,
        Dictionary<string, string[]> wrapperTaskDefinitions)
    {
        var foundTaskDefinitionsInWrapperXml = new List<string>();

        foreach (var wrapperNode in GetConfigRoot(document).Elements())
        {
            var wrapperName = wrapperNode.Name.LocalName;
            var taskNames = new List<string>();

            foreach (var taskNode in wrapperNode.Elements())
            {
                var taskName = taskNode.Name.LocalName;

                if (!taskDefinitions.ContainsKey(taskName))
                {
                    continue;
                }

                if (foundTaskDefinitionsInWrapperXml.Contains(taskName, StringComparer.OrdinalIgnoreCase))
                {
                    continue;
                }

                foundTaskDefinitionsInWrapperXml.Add(taskName);
                taskNames.Add(taskName);
            }

            wrapperTaskDefinitions[wrapperName] = taskNames.ToArray();
        }

        var tasksWithoutWrapper = new List<string>();

        foreach (var taskDefinition in taskDefinitions)
        {
            if (foundTaskDefinitionsInWrapperXml.Contains(taskDefinition.Key, StringComparer.OrdinalIgnoreCase))
            {
                continue;
            }

            tasksWithoutWrapper.Add(taskDefinition.Key);
        }

        foreach (var taskWithoutWrapper in tasksWithoutWrapper)
        {
            wrapperTaskDefinitions[taskWithoutWrapper] = [taskWithoutWrapper];
        }
    }

    private static Dictionary<string, DeviceInputFileDetails> CopyAllDeviceInputInformation(
        Dictionary<string, DeviceInputFileDetails> deviceInputInformation)
    {
        var result = new Dictionary<string, DeviceInputFileDetails>(StringComparer.OrdinalIgnoreCase);

        foreach (var entry in deviceInputInformation)
        {
            result[entry.Key] = entry.Value.Copy();
        }

        return result;
    }

    private static XDocument LoadDocument(string folderPath, string fileName)
    {
        var filePath = ResolveFilePath(folderPath, fileName);

        if (filePath is null)
        {
            throw new FileNotFoundException($"Required XML file not found: {fileName} or {fileName}.xml");
        }

        var document = XDocument.Load(filePath);
        GetConfigRoot(document);

        return document;
    }

    private static string? ResolveFilePath(string folderPath, string fileName)
    {
        var filePathWithoutExtension = Path.Combine(folderPath, fileName);
        if (File.Exists(filePathWithoutExtension))
        {
            return filePathWithoutExtension;
        }

        var filePathWithExtension = Path.Combine(folderPath, fileName + ".xml");
        if (File.Exists(filePathWithExtension))
        {
            return filePathWithExtension;
        }

        return null;
    }

    private static XElement GetConfigRoot(XDocument document)
    {
        if (document.Root is null || document.Root.Name.LocalName != ConfigRootName)
        {
            throw new InvalidOperationException($"XML root node must be '{ConfigRootName}'.");
        }

        return document.Root;
    }

    private static string ReadAttribute(XElement element, string attributeName)
    {
        return ReadOptionalAttribute(element, attributeName) ?? string.Empty;
    }

    private static string? ReadOptionalAttribute(XElement element, string attributeName)
    {
        return element.Attribute(attributeName)?.Value;
    }

    private static string ReadRequiredElementValue(XElement element, string elementName)
    {
        var value = element.Element(elementName)?.Value;

        if (string.IsNullOrWhiteSpace(value))
        {
            throw new InvalidOperationException($"Missing required element '{elementName}' in '{element.Name.LocalName}'.");
        }

        return value;
    }

    private static string ReadOptionalElementValue(XElement element, string elementName, string defaultValue)
    {
        var value = element.Element(elementName)?.Value;
        return string.IsNullOrWhiteSpace(value) ? defaultValue : value;
    }

    private static int ReadRequiredIntElementValue(XElement element, string elementName)
    {
        return int.Parse(ReadRequiredElementValue(element, elementName));
    }

    private static string[] ReadRequiredStringArrayElementValue(XElement element, string elementName)
    {
        return SplitCsv(ReadRequiredElementValue(element, elementName));
    }

    private static string[]? ReadOptionalStringArrayElementValue(XElement element, string elementName)
    {
        var value = element.Element(elementName)?.Value;
        return string.IsNullOrWhiteSpace(value) ? null : SplitCsv(value);
    }

    private static int ReadOptionalIntElementValue(XElement element, string elementName, int defaultValue)
    {
        var value = element.Element(elementName)?.Value;
        return string.IsNullOrWhiteSpace(value) ? defaultValue : Convert.ToInt32(value);
    }

    private static TimeOffsetConfiguration ReadTimeOffsetConfiguration(XElement markerInputNode)
    {
        var timeOffsetNode = markerInputNode.Element("TimeOffset");
        var timeOffset = new TimeOffsetConfiguration();

        if (timeOffsetNode is null)
        {
            return timeOffset;
        }

        timeOffset.FilePrefix = ReadOptionalAttribute(timeOffsetNode, "filePrefix") ?? string.Empty;
        timeOffset.FilePostfix = ReadOptionalAttribute(timeOffsetNode, "filePostfix") ?? string.Empty;
        timeOffset.FileExtension = ReadOptionalAttribute(timeOffsetNode, "fileExtension") ?? string.Empty;
        timeOffset.TimeOffsetHookName = ReadOptionalAttribute(timeOffsetNode, "timeOffsetHookName") ?? string.Empty;
        timeOffset.FixedTimeOffsetValue = ReadOptionalDoubleAttribute(timeOffsetNode, "fixedTimeOffsetValue", 0);
        timeOffset.UseFixedTimeOffsetValue = ReadOptionalBoolAttribute(timeOffsetNode, "useFixedTimeOffsetValue", true);

        return timeOffset;
    }

    private static TimeOffsetConfiguration ReadTimeOffsetConfigurationOverride(
        XElement inputNode,
        TimeOffsetConfiguration referenceDetails)
    {
        var timeOffsetNode = inputNode.Element("TimeOffset");

        if (timeOffsetNode is null)
        {
            return referenceDetails.Copy();
        }

        return new TimeOffsetConfiguration
        {
            FilePrefix = ReadOptionalAttribute(timeOffsetNode, "filePrefix") ?? referenceDetails.FilePrefix,
            FilePostfix = ReadOptionalAttribute(timeOffsetNode, "filePostfix") ?? referenceDetails.FilePostfix,
            FileExtension = ReadOptionalAttribute(timeOffsetNode, "fileExtension") ?? referenceDetails.FileExtension,
            TimeOffsetHookName = ReadOptionalAttribute(timeOffsetNode, "timeOffsetHookName") ?? referenceDetails.TimeOffsetHookName,
            FixedTimeOffsetValue = ReadOptionalDoubleAttribute(
                timeOffsetNode,
                "fixedTimeOffsetValue",
                referenceDetails.FixedTimeOffsetValue),
            UseFixedTimeOffsetValue = ReadOptionalBoolAttribute(
                timeOffsetNode,
                "useFixedTimeOffsetValue",
                referenceDetails.UseFixedTimeOffsetValue)
        };
    }

    private static double ReadOptionalDoubleAttribute(XElement element, string attributeName, double defaultValue)
    {
        var value = ReadOptionalAttribute(element, attributeName);
        return string.IsNullOrWhiteSpace(value)
            ? defaultValue
            : double.Parse(value, CultureInfo.InvariantCulture);
    }

    private static bool ReadOptionalBoolAttribute(XElement element, string attributeName, bool defaultValue)
    {
        var value = ReadOptionalAttribute(element, attributeName);
        return string.IsNullOrWhiteSpace(value) ? defaultValue : Convert.ToBoolean(value);
    }

    private static string ReadFileContentReadHookName(XElement element, string defaultValue = "")
    {
        return ReadOptionalAttribute(element, "fileContentReadHookName") ??
               ReadOptionalAttribute(element, "FileContentReadHookName") ??
               defaultValue;
    }

    private static string[] SplitCsv(string value)
    {
        return value
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
    }

    private static bool ReadBoolAttribute(XElement element, string attributeName)
    {
        var value = ReadOptionalAttribute(element, attributeName);
        return bool.TryParse(value, out var parsedValue) && parsedValue;
    }
}
