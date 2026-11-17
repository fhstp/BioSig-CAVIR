namespace ConsoleApp4;

internal sealed class TimeOffsetConfiguration
{
    public string FilePrefix { get; set; } = string.Empty;

    public string FilePostfix { get; set; } = string.Empty;

    public string FileExtension { get; set; } = string.Empty;

    public string TimeOffsetHookName { get; set; } = string.Empty;

    public double FixedTimeOffsetValue { get; set; }

    public bool UseFixedTimeOffsetValue { get; set; } = true;

    public TimeOffsetConfiguration Copy()
    {
        return new TimeOffsetConfiguration
        {
            FilePrefix = FilePrefix,
            FilePostfix = FilePostfix,
            FileExtension = FileExtension,
            TimeOffsetHookName = TimeOffsetHookName,
            FixedTimeOffsetValue = FixedTimeOffsetValue,
            UseFixedTimeOffsetValue = UseFixedTimeOffsetValue
        };
    }
}
