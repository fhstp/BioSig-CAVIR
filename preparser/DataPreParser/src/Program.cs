namespace ConsoleApp4;

internal static class Program
{
    private const string Version = "Parser Wrapper 0.1.0";
    private static readonly string ConfigPath = Path.Combine(AppContext.BaseDirectory, "config", "main");

    private static int Main(string[] args)
    {
        if (args.Length == 0 || IsHelp(args[0]))
        {
            PrintHelp();
            return 0;
        }

        switch (args[0].ToLowerInvariant())
        {
            case "version":
                Console.WriteLine(Version);
                return 0;

            case "parse":
                return RunParse(args[1..]);

            default:
                Console.Error.WriteLine($"Unknown command: {args[0]}");
                PrintHelp();
                return 1;
        }
    }

    private static int RunParse(string[] args)
    {
        var inputPath = ReadOption(args, "--input");
        var inputBatchPath = ReadOption(args, "--input-batch");

        if (string.IsNullOrWhiteSpace(inputPath) && string.IsNullOrWhiteSpace(inputBatchPath))
        {
            Console.Error.WriteLine("Missing required option: --input <folder> or --input-batch <folder>");
            return 1;
        }

        if (!string.IsNullOrWhiteSpace(inputPath) && !string.IsNullOrWhiteSpace(inputBatchPath))
        {
            Console.Error.WriteLine("Use either --input <folder> or --input-batch <folder>, not both.");
            return 1;
        }

        var selectedInputPath = inputPath ?? inputBatchPath;
        if (!Directory.Exists(selectedInputPath))
        {
            Console.Error.WriteLine($"Input folder not found: {selectedInputPath}");
            return 1;
        }

        try
        {
            if (!Directory.Exists(ConfigPath))
            {
                Console.Error.WriteLine($"Config folder not found: {ConfigPath}");
                return 1;
            }

            HookManagement.LoadHooks();

            var config = ParserConfigReader.Load(ConfigPath);

            Console.WriteLine($"Device inputs: {config.DeviceInputInformation.Count}");
            Console.WriteLine($"Marker inputs: {config.MarkerInputInformation.Count}");
            Console.WriteLine($"Task definitions: {config.TaskDefinitions.Count}");
            Console.WriteLine($"Wrapper task definitions: {config.WrapperTaskDefinitions.Count}");
            Console.WriteLine($"File content read hooks: {HookManagement.FileContentReadHooks.Count}");
            Console.WriteLine($"Time offset hooks: {HookManagement.TimeOffsetHooks.Count}");

            if (!string.IsNullOrWhiteSpace(inputPath))
            {
                BatchParser.Run(config, inputPath);
            }
            else
            {
                foreach (var subjectDirectory in Directory.GetDirectories(inputBatchPath!))
                {
                    Console.WriteLine($"Subject: {Path.GetFileName(subjectDirectory)}");
                    BatchParser.Run(config, subjectDirectory);
                }
            }

            Console.WriteLine("Config loaded.");
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(exception.Message);
            return 1;
        }
    }

    private static string? ReadOption(string[] args, string optionName)
    {
        for (var index = 0; index < args.Length - 1; index++)
        {
            if (string.Equals(args[index], optionName, StringComparison.OrdinalIgnoreCase))
            {
                return args[index + 1];
            }
        }

        return null;
    }

    private static bool IsHelp(string value)
    {
        return value is "help" or "-h" or "--help";
    }

    private static void PrintHelp()
    {
        Console.WriteLine(
            """
            Parser Wrapper

            Usage:
              DataPreParser help
              DataPreParser version
              DataPreParser parse --input <folder>
              DataPreParser parse --input-batch <folder>

            Commands:
              parse      Loads config from .\config\main and scans one subject folder or a folder of subject folders.
              version    Prints the tool version.
              help       Prints this help text.
            """);
    }
}
