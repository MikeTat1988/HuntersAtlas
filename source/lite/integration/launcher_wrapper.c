#define UNICODE
#define _UNICODE
#include <windows.h>
#include <wchar.h>

int WINAPI wWinMain(HINSTANCE instance,HINSTANCE previous,PWSTR ignored,int show) {
    WCHAR directory[32768], executable[32768], command[32768];
    if(!GetModuleFileNameW(NULL,directory,32768)) return 2;
    WCHAR *slash=wcsrchr(directory,L'\\'); if(!slash) return 2; *slash=0;
    if(swprintf_s(executable,32768,L"%s\\Bloodborne.stock.exe",directory)<0) return 2;
    const WCHAR *args=GetCommandLineW();
    if(*args==L'"') {args++;while(*args && *args!=L'"')args++;if(*args)args++;}
    else {while(*args && *args!=L' ' && *args!=L'\t')args++;}
    while(*args==L' ' || *args==L'\t')args++;
    BOOL role=(!wcsncmp(args,L"--script",8) && (!args[8] || args[8]==L' ')) ||
              (!wcsncmp(args,L"--run",5) && (!args[5] || args[5]==L' '));
    int count=role ? swprintf_s(command,32768,L"\"%s\" %s",executable,args) :
        swprintf_s(command,32768,L"\"%s\" --script \"%s\\atlas-lite-launcher.py\" %s",executable,directory,args);
    if(count<0)return 2;
    STARTUPINFOW startup;GetStartupInfoW(&startup);startup.cb=sizeof(startup);
    PROCESS_INFORMATION process;
    if(!CreateProcessW(executable,command,NULL,NULL,TRUE,0,NULL,directory,&startup,&process)) {
        MessageBoxW(NULL,L"Hunter's Atlas launcher files are missing. Run Uninstall.cmd or reinstall Atlas.",L"Bloodborne",MB_OK|MB_ICONERROR);
        return 2;
    }
    CloseHandle(process.hThread);WaitForSingleObject(process.hProcess,INFINITE);
    DWORD result=1;GetExitCodeProcess(process.hProcess,&result);CloseHandle(process.hProcess);
    return (int)result;
}
