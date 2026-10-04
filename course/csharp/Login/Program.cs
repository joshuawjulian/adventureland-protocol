// Login/Program.cs: log in over HTTP, then list the game servers and your characters.
// Run (in course/csharp):
//   First run:  AL_EMAIL=you@example.com AL_PASSWORD=... dotnet run --project Login
//   Later runs: AL_AUTH=<user>-<auth> dotnet run --project Login   (the first run prints this value)
using Albot;

try
{
    var auth = await Api.LoginAsync();
    Console.WriteLine($"user id: {auth.User}");
    var (servers, characters) = await Api.ServersAndCharactersAsync(auth);

    // AL_SERVER is region + name, for example "EUI".
    Console.WriteLine("servers (AL_SERVER, players, address, path):");
    foreach (var s in servers)
        Console.WriteLine($"  {s.Id,-8} {s.Players,3}  {s.Address}  {s.Path}");

    // AL_CHARACTER is the name. The socket `auth` needs the id (CH_...); albot finds it.
    Console.WriteLine("characters (AL_CHARACTER, class, level, id, status):");
    foreach (var c in characters)
    {
        var status = c.Server is null ? "offline" : $"online on {c.Server}"; // server: only while online
        Console.WriteLine($"  {c.Name,-8} {c.Type,-9} {c.Level,3}  {c.Id}  {status}");
    }
}
catch (Exception e)
{
    Console.Error.WriteLine(e.Message);
    return 1;
}
return 0;
