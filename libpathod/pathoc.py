import sys, os
from collections import namedtuple
from netlib import tcp, http
import netlib.utils
import language, utils


class PathocError(Exception): pass
PathocResult = namedtuple('PathocResult', 'httpversion code msg headers content')


class Pathoc(tcp.TCPClient):
    def __init__(self, host, port, ssl=None, sni=None, clientcert=None):
        tcp.TCPClient.__init__(self, host, port)
        self.settings = dict(
            staticdir = os.getcwd(),
            unconstrained_file_access = True,
        )
        self.ssl, self.sni = ssl, sni
        self.clientcert = clientcert

    def http_connect(self, connect_to, wfile, rfile):
        wfile.write(
                    'CONNECT %s:%s HTTP/1.1\r\n'%tuple(connect_to) +
                    '\r\n'
                    )
        wfile.flush()
        rfile.readline()
        headers = http.read_headers(self.rfile)

    def connect(self, connect_to=None):
        """
            connect_to: A (host, port) tuple, which will be connected to with an
            HTTP CONNECT request.
        """
        tcp.TCPClient.connect(self)
        if connect_to:
            self.http_connect(connect_to, self.wfile, self.rfile)
        if self.ssl:
            try:
                self.convert_to_ssl(sni=self.sni, clientcert=self.clientcert)
            except tcp.NetLibError, v:
                raise PathocError(str(v))

    def pipelined_requests(self, specs):
        """
            Return a list of PathocResult namedtuple's.
            The requests defined by the list of spec are sent using http pipelining.

            May raise language.ParseException, netlib.http.HttpError or
            language.FileAccessDenied.
        """
        parsed_specs = {}  # spec -> r, ret
        for spec in specs:
            r = language.parse_request(self.settings, spec)
            ret = language.serve(r, self.wfile, self.settings, self.host)
            parsed_specs[spec] = r, ret
        self.wfile.flush()
        rval = []
        for spec in specs:
            r, ret = parsed_specs[spec]
            result = PathocResult._make(http.read_response(self.rfile, r.method, None))
            rval.append(result)
        return rval

    def request(self, spec):
        """
            Return a PathocResult namedtuple.

            May raise language.ParseException, netlib.http.HttpError or
            language.FileAccessDenied.
        """
        r = language.parse_request(self.settings, spec)
        ret = language.serve(r, self.wfile, self.settings, self.host)
        self.wfile.flush()
        return PathocResult._make(http.read_response(self.rfile, r.method, None))

    def _show_summary(self, fp, pathoc_result):
        print >> fp, "<< %s %s: %s bytes"%(pathoc_result.code, utils.xrepr(pathoc_result.msg), len(pathoc_result.content))

    def _show(self, fp, header, data, hexdump):
        if hexdump:
            print >> fp, "%s (hex dump):"%header
            for line in netlib.utils.hexdump(data):
                print >> fp, "\t%s %s %s"%line
        else:
            print >> fp, "%s (unprintables escaped):"%header
            print >> fp, netlib.utils.cleanBin(data)

    def print_request(self, spec, showreq, showresp, explain, hexdump, ignorecodes, ignoretimeout, fp=sys.stdout):
        """
            Performs a series of requests, and prints results to the specified
            file descriptor.

            spec: A request specification
            showreq: Print requests
            showresp: Print responses
            explain: Print request explanation
            hexdump: When printing requests or responses, use hex dump output
            ignorecodes: Sequence of return codes to ignore

            Returns True if we have a non-ignored response.
        """
        try:
            r = language.parse_request(self.settings, spec)
        except language.ParseException, v:
            print >> fp, "Error parsing request spec: %s"%v.msg
            print >> fp, v.marked()
            return
        except language.FileAccessDenied, v:
            print >> fp, "File access error: %s"%v
            return

        if explain:
            r = r.freeze(self.settings, self.host)

        resp, req = None, None
        if showreq:
            self.wfile.start_log()
        if showresp:
            self.rfile.start_log()
        try:
            req = language.serve(r, self.wfile, self.settings, self.host)
            self.wfile.flush()
            resp = PathocResult._make(http.read_response(self.rfile, r.method, None))
        except http.HttpError, v:
            print >> fp, "<< HTTP Error:", v.msg
        except tcp.NetLibTimeout:
            if ignoretimeout:
                return
            print >> fp, "<<", "Timeout"
        except tcp.NetLibDisconnect: # pragma: nocover
            print >> fp, "<<", "Disconnect"

        if req:
            if ignorecodes and resp and resp.code in ignorecodes:
                return
            if explain:
                print >> fp, ">> Spec:", r.spec()

            if showreq:
                self._show(fp, ">> Request", self.wfile.get_log(), hexdump)

            if showresp:
                self._show(fp, "<< Response", self.rfile.get_log(), hexdump)
            else:
                if resp:
                    self._show_summary(fp, resp)
            return True


    def print_pipelined_requests(self, specs, showreq, showresp, explain, hexdump, ignorecodes, ignoretimeout, fp=sys.stdout):
        """
            Performs a series of pipelined requests, and prints results to the specified
            file descriptor.

            spec: A request specification
            showreq: Print requests
            showresp: Print responses
            explain: Print request explanation
            hexdump: When printing requests or responses, use hex dump output
            ignorecodes: Sequence of return codes to ignore

            Returns True if we have a non-ignored response.
        """
        if explain:
            r = r.freeze(self.settings, self.host)

        if showreq:
            self.wfile.start_log()
        if showresp:
            self.rfile.start_log()

        # write all the requests
        parsed_requests = {}  # spec -> r, req
        for spec in specs:
            try:
                r = language.parse_request(self.settings, spec)
            except language.ParseException, v:
                print >> fp, "Error parsing request spec: %s"%v.msg
                print >> fp, v.marked()
                return
            except language.FileAccessDenied, v:
                print >> fp, "File access error: %s"%v
                return

            req = language.serve(r, self.wfile, self.settings, self.host)
            self.wfile.flush()

            parsed_requests[spec] = r, req

        # read all the responses
        for spec in specs:
            resp = None
            r, req = parsed_requests[spec]
            try:
                resp = http.read_response(self.rfile, r.method, None)
            except http.HttpError, v:
                print >> fp, "<< HTTP Error:", v.msg
            except tcp.NetLibTimeout:
                if ignoretimeout:
                    continue
                print >> fp, "<<", "Timeout"
            except tcp.NetLibDisconnect: # pragma: nocover
                print >> fp, "<<", "Disconnect"

            if req:
                if ignorecodes and resp and resp.code in ignorecodes:
                    continue
                if explain:
                    print >> fp, ">> Spec:", r.spec()

                if showreq:
                    self._show(fp, ">> Request", self.wfile.get_log(), hexdump)

                if showresp:
                    self._show(fp, "<< Response", self.rfile.get_log(), hexdump)
                else:
                    if resp:
                        self._show_summary(fp, resp)

        return True

