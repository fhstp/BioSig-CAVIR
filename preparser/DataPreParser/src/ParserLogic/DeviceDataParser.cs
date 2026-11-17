using System.Globalization;

namespace ConsoleApp4;

internal static class DeviceDataParser
{
    public static void ParseDeviceData(
        string dataFilePath,
        DeviceInputFileDetails deviceInput,
        SortedDictionary<double, string> sortedMarkers,
        Dictionary<string, IFileContentReadHook> fileContentReadHooks,
        Dictionary<string, ITimeOffsetHook> timeOffsetHooks,
        string parsingMainPath,
        string taskName,
        int expectedSections)
    {
        if (string.IsNullOrEmpty(dataFilePath) || !File.Exists(dataFilePath))
        {
            return;
        }

        string delimiter = deviceInput.Delimiter;
        if (delimiter == "tab")
        {
            delimiter = "\t";
        }

        int lineOfFirstData = deviceInput.LineOfFirstData;
        string replaceChar = deviceInput.ReplaceChar;
        string replaceBy = deviceInput.ReplaceBy;
        string useFieldsIndex = deviceInput.UseFieldsIndex;
        int fieldIndexOfTimestamp = deviceInput.FieldIndexOfTimestamp;
        int dropIfCellIsEmpty = deviceInput.DropIfCellIsEmpty;
        double timeStampOffset = TimeOffsetResolver.Resolve(dataFilePath, deviceInput.TimeOffset, timeOffsetHooks);
        string columnTitlesCustom = deviceInput.ColumnTitlesCustom;
        int divider = deviceInput.Divider;

        string outputPath = Path.Combine(parsingMainPath, "output");

        if (!Directory.Exists(outputPath))
        {
            Directory.CreateDirectory(outputPath);
        }

        var sortedDictList = new List<List<string>>();
        var sortedDictTS = new List<double>();

        List<string> allContent = FileContentReader.ReadAllLines(dataFilePath, deviceInput, fileContentReadHooks);
        if (deviceInput.SkipLastLines > 0)
        {
            allContent = allContent
                .Take(Math.Max(0, allContent.Count - deviceInput.SkipLastLines))
                .ToList();
        }

        int lineNumber = 0;
        foreach (string singleContent in allContent)
        {
            string line = singleContent.Replace("\r", string.Empty);
            lineNumber++;

            if (lineNumber <= lineOfFirstData)
            {
                continue;
            }

            if (line.Length < 2)
            {
                continue;
            }

            string[] values = line.Split(new[] { delimiter }, StringSplitOptions.None);
            double timestamp = double.Parse(values[fieldIndexOfTimestamp], CultureInfo.InvariantCulture);

            if (dropIfCellIsEmpty != -1 && values[dropIfCellIsEmpty] == string.Empty)
            {
                continue;
            }

            timestamp = timestamp / divider;
            timestamp += timeStampOffset;

            List<string> rowValues = !string.IsNullOrEmpty(useFieldsIndex)
                ? useFieldsIndex.Split(',').Select(index => values[int.Parse(index)]).ToList()
                : values.ToList();

            if (!string.IsNullOrEmpty(replaceChar))
            {
                rowValues = rowValues.Select(value => value.Replace(replaceChar, replaceBy)).ToList();
            }

            sortedDictTS.Add(timestamp);
            sortedDictList.Add(rowValues);
        }

        var ret = MarkerFileParser.Subselections(sortedMarkers, sortedDictTS, sortedDictList);

        if (expectedSections != -1 && ret.Count != expectedSections)
        {
            string subjectName = Path.GetFileName(
                parsingMainPath.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));

            Console.Error.WriteLine(
                $"Expected {expectedSections} sections for subject '{subjectName}' on device '{deviceInput.Name}', but found {ret.Count}. Check marker file(s) and device data file.");

            return;
        }

        foreach (var singleFile in ret)
        {
            string outputFileName = Path.Combine(
                outputPath,
                $"{taskName}_{singleFile.Key}_{deviceInput.Name}_preparsed.csv");

            using var writer = new StreamWriter(outputFileName);

            if (!string.IsNullOrEmpty(columnTitlesCustom))
            {
                writer.WriteLine(columnTitlesCustom);
            }

            foreach (var entry in singleFile.Value)
            {
                writer.WriteLine(
                    $"{entry.timestamp.ToString(CultureInfo.InvariantCulture)},{string.Join(",", entry.values)}");
            }
        }
    }
}
