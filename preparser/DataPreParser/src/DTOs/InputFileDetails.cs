namespace ConsoleApp4;

internal abstract class InputFileDetails
{
    public string Name { get; set; } = string.Empty;

    public string Prefix { get; set; } = string.Empty;

    public string Suffix { get; set; } = string.Empty;

    public string Extension { get; set; } = string.Empty;

    public string FileContentReadHookName { get; set; } = string.Empty;

    public int SkipLastLines { get; set; }

    public TimeOffsetConfiguration TimeOffset { get; set; } = new();
}
