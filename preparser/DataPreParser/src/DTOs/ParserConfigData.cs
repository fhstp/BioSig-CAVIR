namespace ConsoleApp4;

internal sealed class ParserConfigData
{
    public Dictionary<string, DeviceInputFileDetails> DeviceInputInformation { get; } = new(StringComparer.OrdinalIgnoreCase);

    public Dictionary<string, MarkerInputFileDetails> MarkerInputInformation { get; } = new(StringComparer.OrdinalIgnoreCase);

    public Dictionary<string, TaskDefinition> TaskDefinitions { get; } = new(StringComparer.OrdinalIgnoreCase);

    public Dictionary<string, string[]> WrapperTaskDefinitions { get; } = new(StringComparer.OrdinalIgnoreCase);
}
