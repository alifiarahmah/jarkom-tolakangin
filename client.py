import lib.connection
import lib.segment as segment
import argparse
import os
import socket

class Client:
    def __init__(self, host, port, destPort, outputPath):
        # Init client
        self.host = host
        self.port = port
        self.destPort = destPort
        self.conn = lib.connection.Connection(host,port)
        self.segment = segment.Segment()
        self.outputPath = outputPath
        self.payload = None
        print(f"[!] Client started at {self.host}:{self.port}")

    def three_way_handshake(self):
        # Three Way Handshake, client-side

        # STEP 1: SYN, initiate connection
        print("[!] Initiating three way handshake...")
        self.segment.set_flag([0, 1, 0]) # SYN flag
        seqNum = 0
        self.segment.set_header({
        'seq_num': seqNum,
        'ack_num': 0
        })
        self.conn.send_data(self.segment, (self.host,self.destPort))
        print(f"[!] [Handshake] Sending broadcast SYN request to port {self.destPort}")

        # print(self.segment)
        print("[!] [Handshake] Waiting for response...")

        try:
            data, addr = self.conn.listen_single_segment()
            if data.get_syn() and data.get_ack():
                if data.valid_checksum():
                    print("[!] [Handshake] SYN-ACK received.")

                    # STEP 3: send ACK from client to server
                    data.set_flag([0,0,1])
                    header = data.get_header()
                    serverACK = header['ack_num']
                    serverSeq = header['seq_num']
                    data.set_header({
                    'seq_num': serverACK,
                    'ack_num': serverSeq+1,
                    })
                    self.conn.send_data(data, (self.host,self.destPort))
                    print("[!] [Handshake] Connection established. Sending ACK.")
                    # print(data)
                else:
                    print("[!] [Handhshake] Checksum failed. Connection is terminated.")
        except socket.timeout:
            print("[!] [Handshake] Connection timeout. Connection is terminated.")
            self.close_connection_init()

    def listen_file_transfer(self):
        # File transfer, client-side
        requestNum = 0
        file = open(self.outputPath, "ab", newline=None)
        goBackN = False

        while True:
            try:
                seg, addr = self.conn.listen_single_segment()
                sequenceNum = int(seg.get_header()['seq_num'])
                if (sequenceNum == requestNum):
                    requestNum = sequenceNum + 1
                    if (not seg.get_fin()):
                        file.write(seg.get_payload())
                        seg = segment.Segment()
                        seg.set_flag([0,0,1])
                        seg.set_header({
                            'seq_num': sequenceNum,
                            'ack_num': requestNum,
                        })
                        self.conn.send_data(seg, (self.host,self.destPort))
                        print(f"[Segment SEQ={sequenceNum+1}] received. Ack sent to {self.host}:{self.destPort}")
                    else: # FIN flag
                        file.write(seg.get_payload())
                        seg = segment.Segment()
                        seg.set_flag([1,0,1])
                        seg.set_header({
                            'seq_num': sequenceNum,
                            'ack_num': requestNum,
                        })
                        self.conn.send_data(seg, (self.host,self.destPort))
                        print(f"[Segment SEQ={sequenceNum+1}] received. Ack sent to {self.host}:{self.destPort}")
                        break
                elif (seg.get_fin()):
                    file.close()
                    self.close_connection()
                else:
                    seg.set_flag([0,0,0])
                    seg.set_header({
                        'ack_num': requestNum,
                    })
                    goBackN = True
                    self.conn.send_data(seg, (self.host,self.destPort))
                    print(f"[Segment SEQ={sequenceNum+1}] damaged. Ack {sequenceNum} sent to {self.host}:{self.destPort}")
            except socket.timeout:
                print("[!] [Timeout] No response from server. Connection is terminated.")
                self.close_connection_init()
                break
        
        if (goBackN):
            print("[!] Go-Back-N protocol success.")
        print("[!] File transfer completed.\n")
        
        file.close()
        self.close_connection()

    def close_connection(self):
        print("[!] Closing connection...")
        
        try:
            rcvFIN, addr = self.conn.listen_single_segment()
            if (rcvFIN.get_fin() and addr[1] == self.destPort):
                print(f"[!] Received FIN from {addr[0]}:{addr[1]}")
                tw1 = segment.Segment()
                tw1.set_flag([0,0,1])
                self.conn.send_data(tw1, (self.host,self.destPort))
                print(f"[!] Sending ACK to server")

            tw2 = segment.Segment()
            tw2.set_flag([1,0,0])
            print(f"[!] Sending FIN to server")
            self.conn.send_data(tw2, (self.host,self.destPort))

            rcvACK, addr = self.conn.listen_single_segment()
            if (rcvACK.get_ack() and addr[1] == self.destPort):
                print(f"[!] Received ACK from {addr[0]}:{addr[1]}")
                print(f"[!] Connection closed with server\n")
        except socket.timeout:
            print("[!] [Timeout] No response from server. Connection is terminated.")
        
        # close client socket
        self.conn.close_socket()

    def close_connection_init(self):
        # Close connection, client-side
        print("[!] Closing connection...")
        
        fin = segment.Segment()
        fin.set_flag([1,0,0])
        print("[!] Sending FIN to server...")
        self.conn.send_data(fin, (self.host,self.destPort))

        try:
            print("[!] Waiting for server response...")
            fw1, addr = self.conn.listen_single_segment()
            if fw1.get_ack():
                print("[!] Received ACK from server")

            fw2, addr = self.conn.listen_single_segment()
            if fw2.get_fin():
                print("[!] Received FIN from server")

            tw = segment.Segment()
            tw.set_flag([0,0,1])
            print("[!] Sending ACK to server...")
            self.conn.send_data(tw, (self.host,self.destPort))
            print("[!] Connection closed with server")
        except socket.timeout:
            print("[!] [Timeout] No response from server. Connection is terminated.")

        # close client socket
        self.conn.close_socket()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("clientPort", type=int)
    parser.add_argument("broadcastPort", type=int)
    parser.add_argument("outputPath", type=str)
    args = parser.parse_args()

    # Delete if previous file exist
    try:
        os.remove(args.outputPath)
    except OSError:
        pass

    main = Client('localhost', args.clientPort, args.broadcastPort, args.outputPath)
    
    main.three_way_handshake()
    main.listen_file_transfer()
