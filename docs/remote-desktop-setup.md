# Remote Desktop Setup for Ubuntu 24.04 AWS EC2

This guide explains how to set up remote desktop access on an Ubuntu 24.04 AWS EC2 instance so you can connect from a Windows machine.

## System Information

This setup is tested on:
- **OS**: Ubuntu 24.04 LTS (AWS EC2)
- **Architecture**: x86_64
- **Kernel**: Linux 6.14.0-1011-aws

## Option 1: XRDP (Recommended for Windows RDP)

XRDP allows you to use Windows' built-in Remote Desktop Connection to connect to your Ubuntu machine.

### Installation Steps

1. **Update the system**:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

2. **Install desktop environment (XFCE - lightweight)**:
   ```bash
   sudo apt install -y xfce4 xfce4-goodies
   ```

3. **Install XRDP**:
   ```bash
   sudo apt install -y xrdp
   ```

4. **Configure XRDP to use XFCE**:
   ```bash
   echo "xfce4-session" > ~/.xsession
   ```

5. **Start and enable XRDP service**:
   ```bash
   sudo systemctl enable xrdp
   sudo systemctl start xrdp
   ```

6. **Configure firewall** (if ufw is enabled):
   ```bash
   sudo ufw allow 3389
   ```

7. **Set password for ubuntu user**:
   ```bash
   sudo passwd ubuntu
   ```

### Install Firefox Browser

```bash
sudo apt install -y firefox
```

## Option 2: VNC Server (Alternative)

VNC provides cross-platform remote desktop access but requires a separate VNC client.

### Installation Steps

1. **Install VNC server and desktop**:
   ```bash
   sudo apt update
   sudo apt install -y ubuntu-desktop-minimal tigervnc-standalone-server tigervnc-common
   ```

2. **Set VNC password**:
   ```bash
   vncpasswd
   ```

3. **Start VNC server**:
   ```bash
   vncserver :1 -geometry 1920x1080 -depth 24
   ```

4. **Configure firewall**:
   ```bash
   sudo ufw allow 5901
   ```

## AWS Security Group Configuration

**Important**: You must configure your AWS Security Group to allow remote desktop connections.

1. Go to AWS Console → EC2 → Security Groups
2. Select your instance's security group
3. Add inbound rule:
   - **For XRDP**:
     - Type: Custom TCP
     - Port: 3389
     - Source: Your IP address (for security)
   - **For VNC**:
     - Type: Custom TCP
     - Port: 5901
     - Source: Your IP address (for security)

## Connecting from Windows

### Using XRDP (Option 1)
1. Open "Remote Desktop Connection" (built into Windows)
2. Computer: `your-ec2-hostname:3389` or `your-ec2-public-ip:3389`
3. Username: `ubuntu`
4. Password: The password you set with `sudo passwd ubuntu`

### Using VNC (Option 2)
1. Install a VNC client (like RealVNC Viewer)
2. Connect to: `your-ec2-hostname:5901` or `your-ec2-public-ip:5901`
3. Enter the VNC password you set with `vncpasswd`

## Troubleshooting

### XRDP Issues
- **Black screen**: Make sure you set the session with `echo "xfce4-session" > ~/.xsession`
- **Connection refused**: Check if XRDP is running: `sudo systemctl status xrdp`
- **Can't connect**: Verify AWS Security Group allows port 3389

### VNC Issues
- **Display not found**: Start VNC server with `vncserver :1`
- **Connection timeout**: Check AWS Security Group allows port 5901
- **Poor performance**: Try reducing color depth: `vncserver :1 -depth 16`

### General Network Issues
- Verify your EC2 instance's public IP hasn't changed
- Check that your home/office IP is allowed in the security group
- Ensure the EC2 instance is running and accessible via SSH

## Security Considerations

- **Limit source IPs**: Always restrict remote desktop access to your specific IP addresses
- **Use strong passwords**: Set complex passwords for user accounts
- **Consider VPN**: For production environments, consider accessing through a VPN
- **Disable when not needed**: Stop XRDP/VNC services when not in use:
  ```bash
  sudo systemctl stop xrdp  # For XRDP
  vncserver -kill :1        # For VNC
  ```

## Performance Tips

- **XFCE is lightweight**: We chose XFCE desktop environment for better performance over RDP
- **Adjust resolution**: Use appropriate screen resolution for your connection speed
- **Close unused applications**: Remote desktop uses bandwidth, so close unnecessary programs
- **Use compression**: Some RDP clients offer compression options for slower connections