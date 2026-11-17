using System.Reflection;
using System.Runtime.Loader;

namespace ConsoleApp4;

internal static class HookManagement
{
    private const string HooksFolderName = "hooks";
    private const string FileContentReadHookFolderName = "FileContentReadHook";
    private const string TimeOffsetHookFolderName = "TimeOffsetHook";

    public static Dictionary<string, IFileContentReadHook> FileContentReadHooks { get; } =
        new(StringComparer.OrdinalIgnoreCase);

    public static Dictionary<string, ITimeOffsetHook> TimeOffsetHooks { get; } =
        new(StringComparer.OrdinalIgnoreCase);

    public static void LoadHooks()
    {
        FileContentReadHooks.Clear();
        TimeOffsetHooks.Clear();

        var hooksRootPath = Path.Combine(AppContext.BaseDirectory, HooksFolderName);

        LoadHookDirectory(
            Path.Combine(hooksRootPath, FileContentReadHookFolderName),
            FileContentReadHooks);

        LoadHookDirectory(
            Path.Combine(hooksRootPath, TimeOffsetHookFolderName),
            TimeOffsetHooks);
    }

    private static void LoadHookDirectory<THook>(
        string hookDirectoryPath,
        Dictionary<string, THook> hooks)
        where THook : class
    {
        if (!Directory.Exists(hookDirectoryPath))
        {
            return;
        }

        foreach (var hookDllPath in Directory.GetFiles(hookDirectoryPath, "*.dll"))
        {
            var hookKey = Path.GetFileNameWithoutExtension(hookDllPath);
            var hook = CreateHookInstance<THook>(hookDllPath);

            if (hook is null)
            {
                continue;
            }

            hooks[hookKey] = hook;
        }
    }

    private static THook? CreateHookInstance<THook>(string hookDllPath)
        where THook : class
    {
        var assembly = AssemblyLoadContext.Default.LoadFromAssemblyPath(Path.GetFullPath(hookDllPath));
        var hookType = GetHookTypes<THook>(assembly)
            .OrderBy(type => type.FullName, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();

        if (hookType is null)
        {
            return null;
        }

        return Activator.CreateInstance(hookType) as THook;
    }

    private static IEnumerable<Type> GetHookTypes<THook>(Assembly assembly)
    {
        foreach (var type in GetLoadableTypes(assembly))
        {
            if (type.IsAbstract || type.IsInterface)
            {
                continue;
            }

            if (!typeof(THook).IsAssignableFrom(type))
            {
                continue;
            }

            yield return type;
        }
    }

    private static IEnumerable<Type> GetLoadableTypes(Assembly assembly)
    {
        try
        {
            return assembly.GetTypes();
        }
        catch (ReflectionTypeLoadException exception)
        {
            return exception.Types.Where(type => type is not null)!;
        }
    }
}
