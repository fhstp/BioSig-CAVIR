using ConsoleApp4;
using System.Globalization;
using System.Text.Json;
namespace CavirTimeOffset;

public class CavirTimeOffset : ITimeOffsetHook
{
    public double GetTimeOffset(string filePath)
    {
        var lines = File.ReadAllLines(filePath);
        if (lines.Length < 7) { throw new InvalidOperationException($"Expected at least 7 lines in '{filePath}'."); }
        var timeOffsetLine = Uri.UnescapeDataString(lines[6].Trim());
        using var doc = JsonDocument.Parse(timeOffsetLine);
        var iso = doc.RootElement.GetProperty("SlideShowStartDateTime").GetString() ?? throw new InvalidOperationException("SlideShowStartDateTime missing.");
        var dto = DateTimeOffset.Parse(iso, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind);

        return (dto - DateTimeOffset.UnixEpoch).TotalSeconds;
    }
}
