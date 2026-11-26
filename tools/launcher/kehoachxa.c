/* KeHoachXa.exe: chạy python\python.exe app.py nằm cùng thư mục với file .exe.
   Biên dịch: x86_64-w64-mingw32-gcc -O2 -municode -o KeHoachXa.exe kehoachxa.c res.o */
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

int wmain(void) {
    wchar_t dir[MAX_PATH * 2], py[MAX_PATH * 2], app[MAX_PATH * 2], cmd[MAX_PATH * 6];
    DWORD n = GetModuleFileNameW(NULL, dir, MAX_PATH * 2);
    if (!n) return 1;
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = 0;
    swprintf(py, MAX_PATH * 2, L"%ls\\python\\python.exe", dir);
    swprintf(app, MAX_PATH * 2, L"%ls\\app.py", dir);
    if (GetFileAttributesW(py) == INVALID_FILE_ATTRIBUTES || GetFileAttributesW(app) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(NULL, L"Thiếu thư mục python hoặc file app.py cạnh KeHoachXa.exe.\n"
                          L"Hãy giải nén lại nguyên bộ phần mềm rồi chạy lại.",
                    L"Lập kế hoạch Công an xã", MB_ICONERROR);
        return 1;
    }
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleTitleW(L"Lap ke hoach Cong an xa - dong cua so nay de tat phan mem");
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");
    SetCurrentDirectoryW(dir);
    swprintf(cmd, MAX_PATH * 6, L"\"%ls\" \"%ls\"", py, app);

    SetConsoleCtrlHandler(NULL, TRUE);   /* để python tự xử lý khi người dùng đóng cửa sổ */
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(py, cmd, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        wchar_t msg[512];
        swprintf(msg, 512, L"Không chạy được Python (mã lỗi %lu).", GetLastError());
        MessageBoxW(NULL, msg, L"Lập kế hoạch Công an xã", MB_ICONERROR);
        return 1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    if (code != 0) {
        printf("\nPhan mem dung voi loi (ma %lu). Chup man hinh nay gui nguoi ho tro.\nNhan Enter de dong...", code);
        getchar();
    }
    return (int)code;
}
