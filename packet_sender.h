#ifndef PACKET_SENDER_H
#define PACKET_SENDER_H

void forward(int n);
void backward(int n);
void stop(int n);
void idle(int n);
void function(int n, int type);
int initialize(void);
int terminate(void);

#endif