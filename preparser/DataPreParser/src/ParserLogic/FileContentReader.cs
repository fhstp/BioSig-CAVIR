namespace ConsoleApp4;

internal static class FileContentReader
{
    public static List<string> ReadAllLines(
        string filePath,
        InputFileDetails inputFileDetails,
        Dictionary<string, IFileContentReadHook> fileContentReadHooks)
    {
        if (string.IsNullOrWhiteSpace(inputFileDetails.FileContentReadHookName))
        {
            return File.ReadAllLines(filePath).ToList();
        }

        if (!fileContentReadHooks.TryGetValue(inputFileDetails.FileContentReadHookName, out var fileContentReadHook))
        {
            throw new InvalidOperationException(
                $"File content read hook '{inputFileDetails.FileContentReadHookName}' was not found.");
        }

        var preparedContent = fileContentReadHook.GetPreparedFileContent(filePath);
        var lines = new List<string>();

        using var reader = new StringReader(preparedContent);
        while (reader.ReadLine() is { } line)
        {
            lines.Add(line);
        }

        return lines;
    }
}
