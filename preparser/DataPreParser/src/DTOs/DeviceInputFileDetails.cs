namespace ConsoleApp4;

internal sealed class DeviceInputFileDetails : InputFileDetails
{
    public string Delimiter { get; set; } = ",";

    public int LineOfFirstData { get; set; }

    public string ReplaceChar { get; set; } = string.Empty;

    public string ReplaceBy { get; set; } = string.Empty;

    public string UseFieldsIndex { get; set; } = string.Empty;

    public int FieldIndexOfTimestamp { get; set; }

    public int Divider { get; set; } = 1;

    public int DropIfCellIsEmpty { get; set; } = -1;

    public string ColumnTitlesCustom { get; set; } = string.Empty;

    public DeviceInputFileDetails Copy()
    {
        return new DeviceInputFileDetails
        {
            Name = Name,
            Prefix = Prefix,
            Suffix = Suffix,
            Extension = Extension,
            FileContentReadHookName = FileContentReadHookName,
            SkipLastLines = SkipLastLines,
            Delimiter = Delimiter,
            LineOfFirstData = LineOfFirstData,
            ReplaceChar = ReplaceChar,
            ReplaceBy = ReplaceBy,
            UseFieldsIndex = UseFieldsIndex,
            FieldIndexOfTimestamp = FieldIndexOfTimestamp,
            Divider = Divider,
            DropIfCellIsEmpty = DropIfCellIsEmpty,
            ColumnTitlesCustom = ColumnTitlesCustom,
            TimeOffset = TimeOffset.Copy()
        };
    }
}
