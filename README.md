# nvidia-driver-fedora

Driver container NVIDIA per nodi **Fedora 43** (anche immagini bootc, es. k4all), da usare con il
[NVIDIA GPU Operator](https://github.com/NVIDIA/gpu-operator). I driver vengono compilati e caricati dal
container: il sistema operativo del nodo non ha nessun pacchetto NVIDIA installato.

Deriva dalla cartella `fedora/` di [NVIDIA/gpu-driver-container](https://github.com/NVIDIA/gpu-driver-container)
al commit `b63fda1543`, rimossa upstream con `7a164e3067` ("[cleanup] remove unsupported distros and versions").
Licenza Apache 2.0 (vedi [LICENSE](LICENSE)); il driver NVIDIA scaricato in fase di build ha la sua licenza.

## Differenze rispetto all'originale

- base `fedora:43` (dnf5), driver 595.91.07, Go e immagine CUDA aggiornati, `vgpu-util` compilato solo per `DRIVER_TYPE=vgpu`;
- moduli kernel **open** di default (`KERNEL_MODULE_TYPE` impostato dall'operator, `OPEN_KERNEL_MODULES_ENABLED` ancora accettato);
- percorso firmware GSP configurato in `/sys/module/firmware_class/parameters/path` (necessario ai moduli open);
- file `.driver-daemons-status` per lo startup probe degli operator recenti, controllo SELinux sull'host (`hostPID`);
- `kernel-core` / `kernel-modules-core` scaricati da Koji con `curl` quando il kernel del nodo non è più nei repository
  (corretto anche il nome `kernel-modules-core-<versione>`).

## Immagine

La CI ([.github/workflows/build.yaml](.github/workflows/build.yaml)) costruisce e pubblica:

```
ghcr.io/manustars/driver:595.91.07-fedora43
ghcr.io/manustars/driver:595.91.07-fedora43-<commit>
```

Il suffisso `-fedora43` è obbligatorio: il GPU Operator lo aggiunge da solo alla `driver.version`
leggendo `ID` e `VERSION_ID` del nodo. Prima di pubblicare, la CI compila i moduli contro il kernel del
nodo (input `kernel_version`, default `7.0.12-101.fc43.x86_64`) eseguendo `nvidia-driver update --kernel`.

Dopo il primo push il pacchetto ghcr è privato: renderlo pubblico da
*GitHub → Packages → driver → Package settings → Change visibility*, oppure usare un `imagePullSecret`.

Per un'altra versione: *Actions → Build driver image → Run workflow* con `driver_version` / `fedora_version` / `kernel_version`.

## Uso con il GPU Operator

```yaml
driver:
  enabled: true
  repository: ghcr.io/manustars
  image: driver
  version: "595.91.07"        # l'operator aggiunge "-fedora43"
  kernelModuleType: open
```

Nota: a ogni avvio del pod driver i moduli vengono ricompilati per il kernel in uso (alcuni minuti).
