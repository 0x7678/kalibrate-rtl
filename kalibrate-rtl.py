#!/usr/bin/python3

import argparse
from os.path import isfile
from subprocess import check_output, DEVNULL


class CalTool(object):
    """Machine readable output from kalibrate-rtl."""
    BIN = 'kalibrate-rtl'

    def __init__(self, verbose=False):
        self._verb = verbose

    def _check_output(self, *nargs, **vargs):
        if not self._verb:
            vargs['stderr'] = DEVNULL
        return check_output(*nargs, **vargs)

    def listChannels(self, band):
        """Update list of available BTS, signal strenght etc ...."""
        lines = self._check_output([self.BIN, '-s', band])
        lines = lines.decode('ascii').split('\n')
        chlist = []
        lines = lines[1:]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            _, ch, p = line.split(':')
            ch, freq = ch.strip().split('(')
            ch = int(ch)
            if freq.find('+') >= 0:
                freq, freq_err = freq.strip().split('+')
            else:
                freq, freq_err = freq.strip().split('-')
                freq_err = '-' + freq_err.strip()
            freq = float(freq.strip().rstrip('MHz'))
            freq_err = float(freq_err.strip().rstrip('power').strip().rstrip('kHz)'))
            p = float(p.strip())
            chlist.append( (band, ch, freq, freq_err, p, ) )
        return chlist

    def measurePPM(self, band, channel):
        """Measure and return PPM relative to selected BTS."""
        lines = self._check_output(
                [self.BIN, '-b', band, '-c', str(channel)], timeout=10)
        lines = lines.decode('ascii')
        _, ppm = lines.split('average absolute error:')
        ppm, _ = ppm.strip().split(maxsplit=1)
        return float(ppm.strip())

    def measureMeanPPM(self, channels):
        """Return mean PPM based on error on 'channels'."""
        ppms = []
        ppm = 0.
        pwr = 0.
        for ch in channels:
            _ppm = self.measurePPM(ch[0], ch[1])
            ppms.append( _ppm, )
            ppm += _ppm * ch[4]
            pwr += ch[4]
        ppm /= pwr
        ppm_err = max([abs(_ppm - ppm)  for _ppm in ppms])
        return (ppm, ppm_err, )


class BTSChannels(list):
    HDR = 'band,channel,freq (MHz),freq deviation (kHz),power'

    def __init__(self, src):
        super().__init__(self)
        if issubclass(type(src), str):
            fch = open(src, 'rt')
            hdr = fch.readline().strip()
            if hdr != self.HDR:
                raise ValueError(
                        "Invalid channel list header: '%s', expected '%s'" %
                        (hdr, self.HDR, ))
            for l in fch:
                l = l.split(',')
                l = ( l[0], int(l[1]), float(l[2]), float(l[3]), float(l[4]), )
                self.append(l)
            return
        elif issubclass(type(src), list):
            return self.extend(src)
        raise ValueError("BTS channels can be read from file or from list()")

    def save(self, fname):
        with open(fname, 'wt') as fch:
            fch.write(self.HDR + '\n')
            for ch in self:
                fch.write('%s,%d,%f,%f,%.2f\n' % ch)

    def getBest(self, nchannels=3, max_freq_err=0.6):
        """Return 'n' best channels for PPM calibration."""
        channels = self[:]
        while channels:
            f_mean = sum([c[3] for c in channels]) / len(channels)
            _f_err, _idx = 0., -1
            for idx in range(0, len(channels)):
                f_err = abs(channels[idx][3] - f_mean)
                if f_err > _f_err:
                    _f_err, _idx = f_err, idx
            if _f_err < max_freq_err:
                break
            channels.pop(_idx)

        # get top N BTS with strongest signal
        channels.sort(key=lambda c: -c[4])
        return channels[:nchannels]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description='Evaluate PPM error of SDR, use GSM BTS as reference.')
    parser.add_argument('-b', '--band', type=str,
            help='Select GSM band [GSM850, GSM-R, GSM900, EGSM, DCS, PCS]')
    parser.add_argument('-c', '--channellist', default='bts_channels.csv',
            help='Name of file storing channel list')
    parser.add_argument('-n', '--nchannels', default=3, type=int,
            help='use N channels to measure PPM error default is 3.')
    parser.add_argument('-s', '--scan', default=False, action='store_const',
            const=True, help='Force channel scan.')
    parser.add_argument('-v', '--verbose', default=False, action='store_true',
            help='Print some debug info into stderr.')

    args = parser.parse_args()
    tool = CalTool(verbose=args.verbose)
    if not args.scan and not isfile(args.channellist):
        channellist = args.channellist + '.csv'
        if not isfile(channellist):
            args.scan = True
        else:
            args.channellist = channellist
    if args.scan:
        if not args.band:
            parser.print_help()
            exit(1)
        channels = BTSChannels(tool.listChannels(args.band))
        channels.save(args.channellist)
    else:
        channels = BTSChannels(args.channellist)

    ppm = tool.measureMeanPPM(channels.getBest(args.nchannels))
    print("%.2fppm +-%f" % ppm)

