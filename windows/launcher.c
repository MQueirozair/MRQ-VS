/* mrq-vs.exe — launcher do pacote Windows.
 *
 * Por que existe: o python.exe embeddable é uma build sem console próprio e
 * sem argumentos por omissão; quando o usuário dá dois cliques, o processo
 * abre e fecha em milissegundos (o "não abre"). Este launcher:
 *   1) resolve o caminho do runtime relativo ao próprio executável,
 *   2) passa o .pyz explicitamente (não depende de ._pth),
 *   3) espera o processo terminar e devolve o código de saída,
 *   4) se algo falhar, NÃO fecha calado: imprime o motivo e espera um Enter.
 */
#include <windows.h>
#include <stdio.h>

static void hold(int interactive) {
    if (!interactive) return;
    fputs("\nPressione Enter para fechar...", stderr);
    fflush(stderr);
    getchar();
}

static void fail(const wchar_t *msg, DWORD err, int interactive) {
    fwprintf(stderr, L"\nMRQ VS nao conseguiu iniciar.\n%s\n", msg);
    if (err) fwprintf(stderr, L"Codigo de erro do Windows: %lu\n", err);
    hold(interactive);
}

int main(int argc, char **argv) {
    wchar_t exe[MAX_PATH * 2];
    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH * 2);
    if (n == 0 || n >= MAX_PATH * 2) { fail(L"Caminho do programa invalido.", GetLastError(), 1); return 1; }

    /* corta o nome do arquivo: fica a pasta do pacote */
    wchar_t base[MAX_PATH * 2];
    wcscpy(base, exe);
    for (DWORD i = n; i > 0; i--) {
        if (base[i - 1] == L'\\') { base[i - 1] = 0; break; }
    }

    wchar_t python[MAX_PATH * 2], pyz[MAX_PATH * 2];
    _snwprintf(python, MAX_PATH * 2, L"%s\\runtime\\python.exe", base);
    _snwprintf(pyz, MAX_PATH * 2, L"%s\\app\\run.py", base);

    if (GetFileAttributesW(python) == INVALID_FILE_ATTRIBUTES) {
        fail(L"runtime\\python.exe nao encontrado.\n"
             L"Voce descompactou o zip inteiro? O mrq-vs.exe precisa das pastas\n"
             L"'runtime' e 'app' ao lado dele.", 0, 1);
        return 1;
    }
    if (GetFileAttributesW(pyz) == INVALID_FILE_ATTRIBUTES) {
        fail(L"app\\run.py nao encontrado. Descompacte o pacote completo.", 0, 1);
        return 1;
    }

    /* linha de comando: "<python>" "<pyz>" [args do usuario, em UTF-16] */
    static wchar_t cmd[32768 * 2];
    int p = _snwprintf(cmd, 32768, L"\"%s\" \"%s\"", python, pyz);
    for (int i = 1; i < argc && p < 60000; i++) {
        wchar_t warg[32768];
        if (!MultiByteToWideChar(CP_UTF8, 0, argv[i], -1, warg, 32768)) continue;
        p += _snwprintf(cmd + p, 65536 - p, L" \"%s\"", warg);
    }

    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si)); si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    if (!CreateProcessW(python, cmd, NULL, NULL, TRUE, 0, NULL, base, &si, &pi)) {
        fail(L"Nao foi possivel executar o runtime embutido.", GetLastError(), 1);
        return 1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess); CloseHandle(pi.hThread);

    /* dois cliques sem argumentos: o programa imprime a ajuda; segura a tela */
    if (argc <= 1) hold(1);
    return (int)code;
}
