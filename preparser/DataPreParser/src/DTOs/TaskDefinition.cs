namespace ConsoleApp4;

internal sealed class TaskDefinition
{
    public string Name { get; set; } = string.Empty;

    public int ExpectedSections { get; set; } = -1;

    public DeviceInputFileDetails[] DeviceInputs { get; set; } = []; //maybe Dictionaries later, so overrides can be done by direct lookup

    public MarkerInputFileDetails[] MarkerInputs { get; set; } = [];//maybe Dictionaries later, so overrides can be done by direct lookup
}
