namespace ConsoleApp4;

internal static class TimeOffsetResolver
{
    public static double Resolve(
        string sourceFilePath,
        TimeOffsetConfiguration timeOffset,
        Dictionary<string, ITimeOffsetHook> timeOffsetHooks)
    {
        if (timeOffset.UseFixedTimeOffsetValue)
        {
            return timeOffset.FixedTimeOffsetValue;
        }

        if (!timeOffsetHooks.TryGetValue(timeOffset.TimeOffsetHookName, out var timeOffsetHook))
        {
            throw new InvalidOperationException($"Time offset hook '{timeOffset.TimeOffsetHookName}' was not found.");
        }

        var sourceFileDirectory = Path.GetDirectoryName(sourceFilePath) ?? string.Empty;
        var timeOffsetFile = BatchParser.FindFiles(
                sourceFileDirectory,
                timeOffset.FilePrefix,
                timeOffset.FilePostfix,
                timeOffset.FileExtension,
                expectedFileCount: 1)
            .Single();

        return timeOffsetHook.GetTimeOffset(timeOffsetFile);
    }
}
