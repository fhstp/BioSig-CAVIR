using System.Globalization;

namespace ConsoleApp4;

internal static class MarkerFileParser
{
    public static SortedDictionary<double, string> Parse(
        string filePath,
        MarkerInputFileDetails markerInput,
        SortedDictionary<double, string> parsedMarkers,
        Dictionary<string, IFileContentReadHook> fileContentReadHooks,
        Dictionary<string, ITimeOffsetHook> timeOffsetHooks)
    {
        Dictionary<string, Tuple<string, double>> endMarkerReplacementStartMarker = new Dictionary<string, Tuple<string, double>>();
        Dictionary<string, string> markerAliasLookUp = new Dictionary<string, string>();

        string columnDelimiter = markerInput.ColumnDelimiter;
        int lineOfFirstData = markerInput.LineOfFirstData;
        int fieldIndexOfTimestamp = markerInput.FieldIndexOfTimestamp;
        int fieldIndexOfMarkers = markerInput.FieldIndexOfMarkers;
        string[] markerNumbers = markerInput.MarkerNumbers;
        string[] markerAliases = markerInput.MarkerAliases;
        string[] endingMarkers = markerInput.EndingMarkers;

        string[]? ignoreMarkers = markerInput.IgnoreMarkers;
        string[]? replaceMarkerBefore = markerInput.ReplaceMarkerBefore;
        int expectedColumnCount = markerInput.ExpectedColumnCount;
        int minLineChars = markerInput.MinLineChars;
        int divider = markerInput.Divider;
        double timeOffsetValue = TimeOffsetResolver.Resolve(filePath, markerInput.TimeOffset, timeOffsetHooks);

        for (int index = 0; index < markerNumbers.Length && index < markerAliases.Length; index++)
        {
            markerAliasLookUp.Add(markerNumbers[index], markerAliases[index]);
        }

        List<string> allContent = FileContentReader.ReadAllLines(filePath, markerInput, fileContentReadHooks);
        if (markerInput.SkipLastLines > 0)
        {
            allContent = allContent
                .Take(Math.Max(0, allContent.Count - markerInput.SkipLastLines))
                .ToList();
        }

        //addition for a bunch of first files that haven't a startMarker in Cavir 5
        if (replaceMarkerBefore != null)
        {
            int lineNumber = 0;
            string prevMarkerValue = string.Empty;

            foreach (string singleContent in allContent)
            {
                string line = singleContent;

                lineNumber++;

                if (lineNumber < lineOfFirstData)
                {
                    continue;
                }

                if (line.Length < minLineChars)
                {
                    continue;
                }

                string[] values = line.Split(new[] { columnDelimiter }, StringSplitOptions.None);

                if (expectedColumnCount > -1 && values.Length != expectedColumnCount)
                {
                    continue;
                }

                if (!HasRequiredFields(values, fieldIndexOfTimestamp, fieldIndexOfMarkers))
                {
                    continue;
                }

                if (double.TryParse(values[fieldIndexOfTimestamp], NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out double relativeTimestamp))
                {
                    double absoluteTimestamp = relativeTimestamp / divider + timeOffsetValue;
                    string markerValue = values[fieldIndexOfMarkers];

                    if (replaceMarkerBefore.Length >= 3 &&
                        markerValue != prevMarkerValue &&
                        markerValue == replaceMarkerBefore[0])
                    {
                        endMarkerReplacementStartMarker.Add(
                            markerValue,
                            new Tuple<string, double>(
                                replaceMarkerBefore[1],
                                absoluteTimestamp - Convert.ToDouble(replaceMarkerBefore[2], CultureInfo.InvariantCulture)));
                    }

                    prevMarkerValue = markerValue;
                }
            }
        }
        //actual parsing
        {
            int lineNumber = 0;
            string prevMarkerValue = string.Empty;
            bool nextShouldBeEndingMarkers = false;
            double prevAbsoluteTimestamp = 0;

            foreach (string singleContent in allContent)
            {
                string line = singleContent;

                lineNumber++;

                if (lineNumber < lineOfFirstData)
                {
                    continue;
                }

                if (line.Length < minLineChars)
                {
                    continue;
                }

                string[] values = line.Split(new[] { columnDelimiter }, StringSplitOptions.None);

                if (expectedColumnCount > -1 && values.Length != expectedColumnCount)
                {
                    continue;
                }

                if (!HasRequiredFields(values, fieldIndexOfTimestamp, fieldIndexOfMarkers))
                {
                    continue;
                }

                if (double.TryParse(values[fieldIndexOfTimestamp], NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out double relativeTimestamp))
                {
                    double absoluteTimestamp = prevAbsoluteTimestamp = relativeTimestamp / divider + timeOffsetValue;
                    string markerValue = values[fieldIndexOfMarkers];

                    if (ignoreMarkers != null && ignoreMarkers.Any(ignoreMarker => markerValue == ignoreMarker))
                    {
                        continue;
                    }

                    if (markerValue != "0" && markerValue != prevMarkerValue)
                    {
                        if (nextShouldBeEndingMarkers && !endingMarkers.Any(endingMarker => markerValue == endingMarker))
                        {
                            AddMarker(prevMarkerValue + "_manualEnd", absoluteTimestamp - 0.1, ref markerAliasLookUp, ref parsedMarkers, true);
                            nextShouldBeEndingMarkers = false;
                        }

                        if (!nextShouldBeEndingMarkers && endingMarkers.Any(endingMarker => markerValue == endingMarker))
                        {
                            if (endMarkerReplacementStartMarker.ContainsKey(markerValue))
                            {
                                AddMarker(endMarkerReplacementStartMarker[markerValue].Item1, endMarkerReplacementStartMarker[markerValue].Item2, ref markerAliasLookUp, ref parsedMarkers, false);
                                AddMarker(markerValue, absoluteTimestamp, ref markerAliasLookUp, ref parsedMarkers, true);
                                prevMarkerValue = markerValue;
                                continue;
                            }

                            continue;
                        }

                        AddMarker(markerValue, absoluteTimestamp, ref markerAliasLookUp, ref parsedMarkers, nextShouldBeEndingMarkers);

                        nextShouldBeEndingMarkers = !nextShouldBeEndingMarkers;
                        prevMarkerValue = markerValue;
                    }
                }
            }

            if (nextShouldBeEndingMarkers)
            {
                AddMarker(prevMarkerValue + "_manualFinalEnd", prevAbsoluteTimestamp + 0.1, ref markerAliasLookUp, ref parsedMarkers, true);
            }
        }

        return parsedMarkers;
    }

    private static bool HasRequiredFields(string[] values, int fieldIndexOfTimestamp, int fieldIndexOfMarkers)
    {
        return fieldIndexOfTimestamp >= 0 &&
               fieldIndexOfMarkers >= 0 &&
               fieldIndexOfTimestamp < values.Length &&
               fieldIndexOfMarkers < values.Length;
    }

    public static Dictionary<string, List<TSAndValueList>> Subselections(
        SortedDictionary<double, string> markers,
        List<double> tsList,
        List<List<string>> valueList)
    {
        var subselections = new Dictionary<string, List<TSAndValueList>>();

        for (int i = 0; i < markers.Count; i++)
        {
            if (i + 1 >= markers.Count)
            {
                break;
            }

            if (markers.Values.ElementAt(i + 1).Contains("_end"))
            {
                if (markers.Values.ElementAt(i).Contains("_end"))
                {
                    continue;
                }

                double timestampStart = markers.Keys.ElementAt(i);
                string currentMarkerName = markers.Values.ElementAt(i);
                double timestampEnd = markers.Keys.ElementAt(i + 1);

                List<TSAndValueList> currentSubselection = new List<TSAndValueList>();

                int closestStartKeyIndex = FindClosestKeyIndex(tsList, timestampStart);
                int closestEndKeyIndex = FindClosestKeyIndex(tsList, timestampEnd);

                for (int j = closestStartKeyIndex; j <= closestEndKeyIndex; j++)
                {
                    currentSubselection.Add(new TSAndValueList
                    {
                        timestamp = tsList.ElementAt(j),
                        values = valueList.ElementAt(j)
                    });
                }

                subselections[currentMarkerName + DateTimeOffset.Now.ToUnixTimeMilliseconds().ToString()] =
                    currentSubselection;
            }
        }

        return subselections;
    }

    private static int FindClosestKeyIndex(List<double> keys, double targetKey)
    {
        // Get the list of keys from the SortedDictionary
        // Find the index of the closest key by iterating through the list
        int closestIndex = 0;
        double closestDistance = Math.Abs(keys[0] - targetKey);

        for (int i = 1; i < keys.Count; i++)
        {
            double distance = Math.Abs(keys[i] - targetKey);
            if (distance < closestDistance)
            {
                closestDistance = distance;
                closestIndex = i;
            }
        }

        // Return the index of the closest key
        return closestIndex;
    }

    private static void AddMarker(
        string markerValue,
        double absoluteTimestamp,
        ref Dictionary<string, string> markerAliasLookUp,
        ref SortedDictionary<double, string> sortedMarkers,
        bool isEndingMarker)
    {
        string postFix = isEndingMarker ? "_end" : "_start";
        string markerName = markerAliasLookUp.TryGetValue(markerValue, out string? alias)
            ? alias + postFix
            : markerValue + postFix;

        while (sortedMarkers.ContainsKey(absoluteTimestamp))
        {
            absoluteTimestamp += 0.000001;
        }

        sortedMarkers.Add(absoluteTimestamp, markerName);
    }
}
