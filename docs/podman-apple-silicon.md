# Podman on Apple Silicon (M1/M2/M3) - Known Issues & Solutions

## TL;DR - Quick Solution

**Don't use `--prebuilt` with Podman on Apple Silicon. Build locally instead:**

```bash
# ✅ CORRECT - Build for ARM64
./build_and_run.sh --podman

# ❌ WRONG - Causes "proxy already running" error
./build_and_run.sh --prebuilt --podman
```

## The Problem

### Architecture Mismatch
- **Pre-built images**: `linux/amd64` (Intel x86_64)
- **Apple Silicon Macs**: `linux/arm64` (ARM64)
- **Result**: Containers fail to start, Podman proxy gets stuck

### Symptoms
```
WARNING: image platform (linux/amd64) does not match the expected platform (linux/arm64)
...
Error: unable to start container "...": something went wrong with the request: "proxy already running\n"
```

## Solutions

### Option 1: Build Locally with Podman (Recommended)

Build ARM64-native images from source:

```bash
# Complete reset if proxy is stuck
podman compose down --remove-orphans
podman system prune -a -f
podman machine stop
podman machine rm -f podman-machine-default

# Recreate Podman machine
podman machine init --cpus 4 --memory 8192 --disk-size 50
podman machine start

# Build for ARM64 (takes 10-15 minutes first time)
cd /Users/gabe/git/mcp-gateway-registry
./build_and_run.sh --podman
```

**Pros:**
- ✅ Native ARM64 images (better performance)
- ✅ No architecture warnings
- ✅ Reliable container startup

**Cons:**
- ⏱️ Slower first build (10-15 minutes)

### Option 2: Use Docker Desktop (Easiest)

Docker Desktop handles multi-arch images automatically:

```bash
# Stop Podman
podman machine stop

# Install Docker Desktop (if not already)
# Download: https://www.docker.com/products/docker-desktop/

# Use pre-built images with Docker
./build_and_run.sh --prebuilt

# Access at http://localhost (port 80)
```

**Pros:**
- ✅ Fast deployment (2-3 minutes)
- ✅ Pre-built images work reliably
- ✅ Better multi-arch support

**Cons:**
- ⚠️ Requires Docker Desktop
- ⚠️ Uses privileged ports (80/443)

### Option 3: Fix Stuck Proxy Manually

If the proxy is stuck and reset doesn't work:

```bash
# Find stuck gvproxy processes
ps aux | grep gvproxy

# Kill them (replace <PID> with actual process ID)
kill -9 <PID>

# Find stuck Podman processes
ps aux | grep podman | grep -v grep
kill -9 <PID>

# Remove socket files
rm -rf ~/Library/Containers/com.github.containers.podman.*

# Remove state files
rm -rf ~/.config/containers/podman/machine/*
rm -rf ~/.local/share/containers/podman/machine/*

# Recreate Podman machine
podman machine stop
podman machine rm -f podman-machine-default
podman machine init --cpus 4 --memory 8192 --disk-size 50
podman machine start

# Build locally (no --prebuilt!)
./build_and_run.sh --podman
```

## Why This Happens

### The Chain of Events

1. **User runs**: `./build_and_run.sh --prebuilt --podman`
2. **Script pulls**: `linux/amd64` images from Docker Hub
3. **Podman tries**: To run amd64 images on arm64 system
4. **Containers fail**: Due to architecture incompatibility
5. **gvproxy stuck**: Networking proxy doesn't clean up properly
6. **Subsequent attempts**: Fail with "proxy already running"

### Technical Details

- **Podman on macOS**: Runs in a QEMU VM (similar to Docker Desktop)
- **Architecture emulation**: QEMU can emulate amd64 on arm64, but unreliably
- **gvproxy networking**: Podman's networking proxy (`gvproxy`) handles port forwarding
- **Cleanup issues**: When containers crash, proxy doesn't always terminate properly
- **Socket conflicts**: Stuck proxy prevents new containers from binding ports

## Verification

After deployment, verify you're running ARM64 images:

```bash
# Check architecture of running containers
podman inspect <container-name> | grep Architecture

# Should show: "Architecture": "arm64"
# NOT: "Architecture": "amd64"
```

## Performance Comparison

| Method | Architecture | First Deploy | Subsequent Deploys | Reliability |
|--------|--------------|--------------|-------------------|-------------|
| Podman + Local Build | ARM64 (native) | 10-15 min | 2-3 min | ⭐⭐⭐⭐⭐ |
| Podman + Pre-built | AMD64 (emulated) | 2-3 min | 2-3 min | ⭐⭐ (unstable) |
| Docker + Pre-built | AMD64 (emulated) | 2-3 min | 2-3 min | ⭐⭐⭐⭐ |
| Docker + Local Build | ARM64 (native) | 10-15 min | 2-3 min | ⭐⭐⭐⭐⭐ |

## Best Practices

### ✅ DO

- **Build locally** with Podman on Apple Silicon
- **Use Docker Desktop** if you want pre-built images
- **Check architecture** after deployment
- **Reset Podman machine** if you encounter proxy errors

### ❌ DON'T

- **Don't use** `--prebuilt` with Podman on ARM64
- **Don't mix** Docker and Podman (use one at a time)
- **Don't ignore** architecture warnings
- **Don't assume** emulation will work reliably

## Future Improvements

We're working on:
- [ ] ARM64 pre-built images on Docker Hub
- [ ] Multi-arch manifest support
- [ ] Automatic architecture detection in script
- [ ] Better error messages for architecture mismatches

## Additional Resources

- [Podman Documentation](https://docs.podman.io/)
- [Docker Multi-Platform Images](https://docs.docker.com/build/building/multi-platform/)
- [Apple Silicon Support](https://www.docker.com/blog/apple-silicon-m1-chips-and-docker/)

## Still Having Issues?

If you continue to experience problems:

1. **Share full logs**: Include output from `podman machine logs`
2. **System info**: Run `podman info` and share output
3. **Open an issue**: [GitHub Issues](https://github.com/agentic-community/mcp-gateway-registry/issues)
4. **Include details**: Mac model, macOS version, Podman version

## Quick Reference Commands

```bash
# Check your architecture
uname -m  # Should show: arm64

# Check Podman version
podman --version

# Check container architecture
podman inspect <container> | grep Architecture

# Full Podman reset
podman machine stop
podman machine rm -f podman-machine-default
podman system reset -f
podman machine init --cpus 4 --memory 8192 --disk-size 50
podman machine start

# Deploy correctly on Apple Silicon
./build_and_run.sh --podman  # NO --prebuilt!
```

