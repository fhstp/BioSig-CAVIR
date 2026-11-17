namespace ConsoleApp4;

internal sealed class MarkerInputFileDetails : InputFileDetails
{
    public Dictionary<string, Tuple<string, double>> EndMarkerReplacementStartMarker { get; } = new();

    public string ColumnDelimiter { get; set; } = string.Empty;

    public int LineOfFirstData { get; set; }

    public int FieldIndexOfTimestamp { get; set; }

    public int FieldIndexOfMarkers { get; set; }

    public string[] MarkerNumbers { get; set; } = [];

    public string[] MarkerAliases { get; set; } = [];

    public string[] EndingMarkers { get; set; } = [];

    public string[]? IgnoreMarkers { get; set; }

    public string[]? ReplaceMarkerBefore { get; set; }

    public int ExpectedColumnCount { get; set; } = -1;

    public int MinLineChars { get; set; }

    public int Divider { get; set; } = 1;

    public MarkerInputFileDetails Copy()
    {
        var copy = new MarkerInputFileDetails
        {
            Name = Name,
            Prefix = Prefix,
            Suffix = Suffix,
            Extension = Extension,
            ColumnDelimiter = ColumnDelimiter,
            LineOfFirstData = LineOfFirstData,
            FieldIndexOfTimestamp = FieldIndexOfTimestamp,
            FieldIndexOfMarkers = FieldIndexOfMarkers,
            MarkerNumbers = MarkerNumbers.ToArray(),
            MarkerAliases = MarkerAliases.ToArray(),
            EndingMarkers = EndingMarkers.ToArray(),
            IgnoreMarkers = IgnoreMarkers?.ToArray(),
            ReplaceMarkerBefore = ReplaceMarkerBefore?.ToArray(),
            FileContentReadHookName = FileContentReadHookName,
            SkipLastLines = SkipLastLines,
            ExpectedColumnCount = ExpectedColumnCount,
            MinLineChars = MinLineChars,
            Divider = Divider,
            TimeOffset = TimeOffset.Copy()
        };

        foreach (var entry in EndMarkerReplacementStartMarker)
        {
            copy.EndMarkerReplacementStartMarker[entry.Key] = entry.Value;
        }

        return copy;
    }
}
