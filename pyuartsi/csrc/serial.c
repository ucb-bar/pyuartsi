

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <errno.h>


ssize_t serial_init(const char *path, speed_t baudrate, int timeout_ms) {
  printf("[DEBUG] <Serial>: Initializing serial port %s\n", path);


  printf("[DEBUG] baudrate: %i\n", baudrate);

  int fd = open(path, O_RDWR);

  if (fd < 0) {
    printf("[ERROR] <Serial>: Error %i from open: %s\n", errno, strerror(errno));
    return -1;
  }

  struct termios tty;
  memset(&tty, 0, sizeof tty);

  if (tcgetattr(fd, &tty) != 0) {
    printf("[ERROR] <Serial>: Error %i from tcgetattr: %s\n", errno, strerror(errno));
    return -1;
  }

  tty.c_cflag &= ~PARENB;  // Disable parity
  tty.c_cflag &= ~CSTOPB;  // 1 stop bit
  tty.c_cflag &= ~CSIZE;   // Clear the mask
  tty.c_cflag |= CS8;      // 8 data bits
  tty.c_cflag &= ~CRTSCTS; // No hardware flow control
  tty.c_cflag |= CREAD | CLOCAL; // Turn on READ & ignore ctrl lines

  tty.c_lflag &= ~ICANON; // Disable canonical mode
  tty.c_lflag &= ~ECHO;   // Disable echo
  tty.c_lflag &= ~ECHOE;  // Disable erasure
  tty.c_lflag &= ~ECHONL; // Disable new-line echo
  tty.c_lflag &= ~ISIG;   // Disable interpretation of INTR, QUIT and SUSP
  tty.c_iflag &= ~(IXON | IXOFF | IXANY); // Turn off s/w flow ctrl
  tty.c_iflag &= ~(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL); // Disable any special handling of received bytes

  tty.c_oflag &= ~OPOST; // Prevent special interpretation of output bytes (e.g. newline chars)
  tty.c_oflag &= ~ONLCR; // Prevent conversion of newline to carriage return/line feed

  // Wait for up to 1s (10 deciseconds), returning as soon as any data is received.
  tty.c_cc[VTIME] = timeout_ms / 100;
  tty.c_cc[VMIN] = 0;

  if (tcsetattr(fd, TCSANOW, &tty) != 0) {
    printf("[ERROR] <Serial>: Error %i from cfsetattr: %s\n", errno, strerror(errno));
    return -1;
  }

  if (cfsetospeed(&tty, baudrate) != 0) {
    printf("[ERROR] <Serial>: Error %i from cfsetospeed: %s\n", errno, strerror(errno));
    return -1;
  }

  printf("[INFO] <Serial>: Serial port %s initialized\n", path);
  return fd;  
}

ssize_t serial_read(ssize_t fd, char *buf, size_t len) {
  ssize_t n = read(fd, buf, len);
  if (n < 0) {
    printf("[ERROR] <Serial>: Error %i from read: %s\n", errno, strerror(errno));
    return -1;
  }
  return n;
}

ssize_t serial_write(ssize_t fd, const char *buf, size_t len) {
  ssize_t n = write(fd, buf, len);
  if (n < 0) {
    printf("[ERROR] <Serial>: Error %i from write: %s\n", errno, strerror(errno));
    return -1;
  }
  return n;
}



// int main() {
//   ssize_t fd = serial_init("/dev/ttyUSB2", B115200, 1000);
//   if (fd < 0) {
//     printf("[ERROR] <Serial>: Failed to initialize serial port\n");
//     return -1;
//   }

//   printf("[INFO] <Serial>: Serial port initialized\n");

//   char buf[] = "hello\n";

//   serial_write(fd, buf, strlen(buf));

//   char rxbuf[8];

//   ssize_t n = serial_read(fd, rxbuf, sizeof(rxbuf));

//   printf("[INFO] <Serial>: Received %i bytes: %s\n", n, rxbuf);

//   return 0;
// }
