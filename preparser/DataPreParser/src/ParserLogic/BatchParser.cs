using System.Text.RegularExpressions;

namespace ConsoleApp4;

internal static class BatchParser
{
    private const int ExpectedFileCount = 1;

    public static void Run(
        ParserConfigData config,
        string parsingDirectory)
    {
        foreach (var wrapperTaskDefinition in config.WrapperTaskDefinitions)
        {
            var wrapperTaskName = wrapperTaskDefinition.Key;
            var taskNames = wrapperTaskDefinition.Value;
            var wrapperTaskDirectory = Path.Combine(parsingDirectory, wrapperTaskName);

            if (!Directory.Exists(wrapperTaskDirectory))
            {
                continue;
            }

            foreach (var parsingFolderPath in EnumerateParsingFolders(wrapperTaskDirectory))
            {
                var files = Directory.GetFiles(parsingFolderPath);

                foreach (var taskName in taskNames)
                {
                    if (!config.TaskDefinitions.TryGetValue(taskName, out var taskDefinition))
                    {
                        continue;
                    }

                    if (!TryFindMarkerFiles(parsingFolderPath, taskDefinition, out var markerFiles))
                    {
                        continue;
                    }

                    var parsedMarkers = new SortedDictionary<double, string>();

                    foreach (var markerInput in taskDefinition.MarkerInputs)
                    {
                        if (!markerFiles.TryGetValue(markerInput.Name, out var filesForMarkerInput))
                        {
                            continue;
                        }

                        foreach (var markerFile in filesForMarkerInput)
                        {
                            MarkerFileParser.Parse(
                                markerFile,
                                markerInput,
                                parsedMarkers,
                                HookManagement.FileContentReadHooks,
                                HookManagement.TimeOffsetHooks);

                            Console.WriteLine(
                                $"Prepared marker file '{Path.GetFileName(markerFile)}' for task '{taskDefinition.Name}', marker '{markerInput.Name}', parsed markers: {parsedMarkers.Count}, files: {files.Length}");
                        }
                    }

                    var deviceFiles = FindDeviceFiles(parsingFolderPath, taskDefinition);

                    foreach (var deviceInput in taskDefinition.DeviceInputs)
                    {
                        if (!deviceFiles.TryGetValue(deviceInput.Name, out var filesForDeviceInput))
                        {
                            continue;
                        }

                        foreach (var deviceFile in filesForDeviceInput)
                        {
                            DeviceDataParser.ParseDeviceData(
                                deviceFile,
                                deviceInput,
                                parsedMarkers,
                                HookManagement.FileContentReadHooks,
                                HookManagement.TimeOffsetHooks,
                                parsingDirectory,
                                taskDefinition.Name,
                                taskDefinition.ExpectedSections);

                            Console.WriteLine(
                                $"Prepared device file '{Path.GetFileName(deviceFile)}' for task '{taskDefinition.Name}', device '{deviceInput.Name}', files: {files.Length}");
                        }
                    }
                }
            }
        }
    }

    private static IEnumerable<string> EnumerateParsingFolders(string wrapperTaskDirectory)
    {
        yield return wrapperTaskDirectory;

        foreach (var directory in Directory.GetDirectories(wrapperTaskDirectory, "*", SearchOption.AllDirectories))
        {
            yield return directory;
        }
    }

    private static bool TryFindMarkerFiles(
        string directory,
        TaskDefinition taskDefinition,
        out Dictionary<string, List<string>> markerFiles)
    {
        markerFiles = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);

        foreach (var markerInput in taskDefinition.MarkerInputs)
        {
            try
            {
                markerFiles[markerInput.Name] = FindFiles(
                    directory,
                    markerInput.Prefix,
                    markerInput.Suffix,
                    markerInput.Extension,
                    ExpectedFileCount).ToList();
            }
            catch
            {
                return false;
            }
        }

        return true;
    }

    private static Dictionary<string, List<string>> FindDeviceFiles(
        string directory,
        TaskDefinition taskDefinition)
    {
        var deviceFiles = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase);

        foreach (var deviceInput in taskDefinition.DeviceInputs)
        {
            try
            {
                deviceFiles[deviceInput.Name] = FindFiles(
                    directory,
                    deviceInput.Prefix,
                    deviceInput.Suffix,
                    deviceInput.Extension,
                    ExpectedFileCount).ToList();
            }
            catch
            {
                continue;
            }
        }

        return deviceFiles;
    }

    internal static IEnumerable<string> FindFiles(
        string directory,
        string prefix,
        string suffix,
        string extension = "*",
        int expectedFileCount = ExpectedFileCount)
    {
        var effectiveExtension = string.IsNullOrWhiteSpace(extension) ? "*" : extension.TrimStart('.');
        var searchPattern = effectiveExtension == "*" ? "*.*" : "*." + effectiveExtension;
        var pattern = prefix + suffix + ".*";

        var files = Directory.GetFiles(directory, searchPattern)
            .Where(file => Regex.IsMatch(Path.GetFileName(file), pattern))
            .ToList();

        if (files.Count != expectedFileCount)
        {
            throw new Exception(
                $"{suffix}: Expected {expectedFileCount} files but found {files.Count}");
        }

        return files;
    }
}
