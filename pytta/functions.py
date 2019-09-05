# -*- coding: utf-8 -*-
"""
Functions:
-----------

    This submodule carries a set of useful functions of general purpouses when
    using PyTTa, like reading and writing wave files, seeing the audio IO
    devices available and some signal processing tools.

    Available functions:
    ---------------------

        >>> pytta.list_devices()
        >>> pytta.read_wav( fileName )
        >>> pytta.write_wav( fileName, signalObject )
        >>> pytta.save(fileName, obj1, ..., objN)
        >>> pytta.load(fileName)
        >>> pytta.merge( signalObj1, signalObj2, ..., signalObjN )
        >>> pytta.fft_convolve( signalObj1, signalObj2 )
        >>> pytta.find_delay( signalObj1, signalObj2 )
        >>> pytta.corr_coef( signalObj1, signalObj2 )
        >>> pytta.resample( signalObj, newSamplingRate )
        >>> pytta.peak_time(signalObj1, signalObj2, ..., signalObjN )


    For further information, check the function specific documentation.
"""


import os
import time
import json
from scipy.io import wavfile as wf
import scipy.io as sio
import numpy as np
import sounddevice as sd
import scipy.signal as ss
import scipy.fftpack as sfft
import zipfile as zf
import h5py
from pytta.classes import SignalObj, ImpulsiveResponse, \
                    RecMeasure, PlayRecMeasure, FRFMeasure
from pytta.classes._base import ChannelsList, ChannelObj
import copy as cp


def list_devices():
    """
    Shortcut to sounddevice.query_devices(). Made to exclude the need of
    importing Sounddevice directly just to find out which audio devices can be
    used.

        >>> pytta.list_devices()

    """
    return sd.query_devices()


def read_wav(fileName):
    """
    Reads a wave file into a SignalObj
    """
    samplingRate, data = wf.read(fileName)
    if data.dtype == 'int16':
        data = data/(2**15)
    if data.dtype == 'int32':
        data = data/(2**31)
    signal = SignalObj(data, 'time', samplingRate=samplingRate)
    return signal


def write_wav(fileName, signalIn):
    """
    Writes a SignalObj into a single wave file
    """
    samplingRate = signalIn.samplingRate
    data = signalIn.timeSignal
    return wf.write(fileName, samplingRate, data)


# Refactor for new SignalObj's channelsList
def merge(signal1, *signalObjects):
    """
    Gather all of the input argument signalObjs into a single
    signalObj and place the respective timeSignal of each
    as a column of the new object
    """
    j = 1
    comment = cp.deepcopy(signal1.comment)
    channels = cp.deepcopy(signal1.channels)
    timeSignal = cp.deepcopy(signal1.timeSignal)
    for inObj in signalObjects:
        if signal1.samplingRate != inObj.samplingRate:
            message = '\
            \n To merge signals they must have the same sampling rate!\
            \n SignalObj 1 and '+str(j+1)+' have different sampling rates.'
            raise AttributeError(message)
        if signal1.numSamples != inObj.numSamples:
            message = '\
            \n To merge signals they must have the same length!\
            \n SignalObj 1 and '+str(j+1)+' have different lengths.'
            raise AttributeError(message)
        comment = comment + ' / ' + inObj.comment
        for ch in inObj.channels._channels:
            channels.append(ch)
        timeSignal = np.hstack((timeSignal, inObj.timeSignal))
        j += 1
    newSignal = SignalObj(timeSignal, domain='time',
                          samplingRate=signal1.samplingRate, comment=comment)
    channels.conform_to()
    newSignal.channels = channels
    return newSignal


# def split(signal):
#    return 0


def fft_convolve(signal1, signal2):
    """
    Uses scipy.signal.fftconvolve() to convolve two time domain signals.

        >>> convolution = pytta.fft_convolve(signal1,signal2)

    """
#    Fs = signal1.Fs
    conv = ss.fftconvolve(signal1.timeSignal, signal2.timeSignal)
    signal = SignalObj(conv, 'time', signal1.samplingRate)
    return signal


def find_delay(signal1, signal2):
    """
    Cross Correlation alternative, more efficient fft based method to calculate
    time shift between two signals.

    >>> shift = pytta.find_delay(signal1,signal2)

    """
    if signal1.N != signal2.N:
        return print('Signal1 and Signal2 must have the same length')
    else:
        freqSignal1 = signal1.freqSignal
        freqSignal2 = sfft.fft(np.flipud(signal2.timeSignal))
        convoluted = np.real(sfft.ifft(freqSignal1 * freqSignal2))
        convShifted = sfft.fftshift(convoluted)
        zeroIndex = int(signal1.numSamples / 2) - 1
        shift = zeroIndex - np.argmax(convShifted)
    return shift


def corr_coef(signal1, signal2):
    """
    Finds the correlation coeficient between two SignalObjs using
    the numpy.corrcoef() function.
    """
    coef = np.corrcoef(signal1.timeSignal, signal2.timeSignal)
    return coef[0, 1]


def resample(signal, newSamplingRate):
    """
        Resample the timeSignal of the input SignalObj to the
        given sample rate using the scipy.signal.resample() function
    """
    newSignalSize = np.int(signal.timeLength*newSamplingRate)
    resampled = ss.resample(signal.timeSignal[:], newSignalSize)
    newSignal = SignalObj(resampled, "time", newSamplingRate)
    return newSignal


def peak_time(signal):
    """
        Return the time at signal's amplitude peak.
    """
    if not isinstance(signal, SignalObj):
        raise TypeError('Signal must be an SignalObj.')
    peaks_time = []
    for chindex in range(signal.num_channels()):
        maxamp = max(np.abs(signal.timeSignal[:, chindex]))
        maxindex = np.where(signal.timeSignal[:, chindex] == np.abs(maxamp))[0]
        maxtime = signal.timeVector[maxindex][0]
        peaks_time.append(maxtime)
    if signal.numChannels > 1:
        return peaks_time
    else:
        return peaks_time[0]


def save(fileName: str = time.ctime(time.time()), *PyTTaObjs):
    """
    Saves any number of PyTTaObj subclasses' objects to fileName.pytta file.

    Just calls .save() method of each class and packs them all into a major
    .pytta file along with a Meta.json file containing the fileName of each
    saved object.

    The .pytta extension must not be appended to the fileName
    """
    meta = {}
    with zf.ZipFile(fileName + '.pytta', 'w') as zdir:
        for idx, obj in enumerate(PyTTaObjs):
            sobj = obj.save('obj' + str(idx))
            meta['obj' + str(idx)] = sobj
            zdir.write(sobj)
            os.remove(sobj)
        with open('Meta.json', 'w') as f:
            json.dump(meta, f, indent=4)
        zdir.write('Meta.json')
        os.remove('Meta.json')
    return fileName + '.pytta'


def h5save(fileName: str, *PyTTaObjs):
    with h5py.File(fileName, 'w') as f:
        objsNameCount = {}
        for idx, pobj in enumerate(PyTTaObjs):
            if isinstance(pobj, (SignalObj,
                                 ImpulsiveResponse,
                                 RecMeasure,
                                 PlayRecMeasure,
                                 FRFMeasure)):
                # Check if creation_name was already used
                creationName = pobj.creation_name
                if creationName in objsNameCount:
                    objsNameCount[creationName] += 1
                    creationName += '_' + str(objsNameCount[creationName])
                else:
                    objsNameCount[creationName] = 1

                ObjGroup = f.create_group(creationName)  # create obj's group
                pobj.h5save(ObjGroup)  # save the obj inside its group
            else:
                print("Only PyTTa objects can be saved through this" +
                      "function. Skipping object number " + str(idx) + ".")


def h5load(fileName: str):
    if fileName.split('.')[-1] != 'hdf5':
        raise ValueError("h5load function only works with *.hdf5 files")
    f = h5py.File(fileName, 'r')
    loadedObjects = {}
    for PyTTaObjName, PyTTaObjGroup in f.items():
        loadedObjects[PyTTaObjName] = __h5_unpack(PyTTaObjGroup)
    f.close()
    return loadedObjects

def __h5_unpack(ObjGroup):
    """
    Unpack an HDF5 group into its respective PyTTa object
    """
    if ObjGroup.attrs['class'] == 'SignalObj':
        samplingRate = ObjGroup.attrs['samplingRate']
        lengthDomain = ObjGroup.attrs['lengthDomain']
        comment = ObjGroup.attrs['comment']
        channels = eval(ObjGroup.attrs['channels'])
        freqMin = __h5_none_parser(ObjGroup.attrs['freqMin'])
        freqMax = __h5_none_parser(ObjGroup.attrs['freqMax'])
        SigObj = SignalObj(signalArray=np.array(ObjGroup['timeSignal']),
                           domain='time',
                           samplingRate=samplingRate,
                           freqMin=freqMin,
                           freqMax=freqMax,
                           comment=comment)
        SigObj.channels = channels
        SigObj.lengthDomain = lengthDomain
        return SigObj

    if ObjGroup.attrs['class'] == 'ImpulsiveResponse':
        excitation = __h5_unpack(ObjGroup['excitation'])
        recording = __h5_unpack(ObjGroup['recording'])
        method = ObjGroup.attrs['method']
        winType = ObjGroup.attrs['winType']
        winSize = ObjGroup.attrs['winSize']
        overlap = ObjGroup.attrs['overlap']
        IR = ImpulsiveResponse(excitation,
                               recording,
                               method,
                               winType,
                               winSize,
                               overlap)
        return IR

    if ObjGroup.attrs['class'] == 'RecMeasure':
        pass

    if ObjGroup.attrs['class'] == 'PlayRecMeasure':
        pass

    if ObjGroup.attrs['class'] == 'FRFMeasure':
        pass    


def __h5_none_parser(attr):
    if attr != 'None' and attr is not None:
        return attr
    elif attr == 'None':
        return None
    elif attr is None:
        return 'None'


def load(fileName: str):
    """
    Loads .pytta files and parses it's types to the correct objects.
    """
    if fileName.split('.')[-1] == 'pytta':
        with zf.ZipFile(fileName, 'r') as zdir:
            objects = zdir.namelist()
            for obj in objects:
                if obj.split('.')[-1] == 'json':
                    meta = obj
            zdir.extractall()
            output = __parse_load(meta)
    else:
        raise ValueError("Load function only works with *.pytta files")
    return output


def __parse_load(className):
    name = className.split('.')[0]
    openJson = json.load(open(className, 'r'))
    if name == 'SignalObj':
        openMat = sio.loadmat(openJson['timeSignalAddress'])
        out = SignalObj(openMat['timeSignal'], domain=openJson['lengthDomain'],
                        samplingRate=openJson['samplingRate'],
                        freqMin=openJson['freqLims'][0],
                        freqMax=openJson['freqLims'][1],
                        comment=openJson['comment'])
        out.channels = __parse_channels(openJson['channels'],
                                        out.channels)
        os.remove(openJson['timeSignalAddress'])

    elif name == 'ImpulsiveResponse':
        excit = load(openJson['SignalAddress']['excitation'])
        record = load(openJson['SignalAddress']['recording'])
        out = ImpulsiveResponse(excit, record, **openJson['methodInfo'])
        os.remove(openJson['SignalAddress']['excitation'])
        os.remove(openJson['SignalAddress']['recording'])

    elif name == 'RecMeasure':
        inch = list(np.arange(len(openJson['inChannels'])))
        out = RecMeasure(device=openJson['device'], inChannels=inch, lengthDomain='samples', fftDegree=openJson['fftDegree'])
        out.inChannels = __parse_channels(openJson['inChannels'],
                                          out.inChannels)

    elif name == 'PlayRecMeasure':
        inch = list(1 + np.arange(len(openJson['inChannels'])))
        excit = load(openJson['excitationAddress'])
        out = PlayRecMeasure(excitation=excit, device=openJson['device'], inChannels=inch)
        out.inChannels = __parse_channels(openJson['inChannels'],
                                          out.inChannels)
        os.remove(openJson['excitationAddress'])

    elif name == 'FRFMeasure':
        inch = list(1 + np.arange(len(openJson['inChannels'])))
        excit = load(openJson['excitationAddress'])
        out = FRFMeasure(excitation=excit, device=openJson['device'], inChannels=inch)
        out.inChannels = __parse_channels(openJson['inChannels'],
                                          out.inChannels)
        os.remove(openJson['excitationAddress'])

    elif name == 'Meta':
        out = []
        for key, val in openJson.items():
            out.append(load(val))
            os.remove(val)
    os.remove(className)
    return out


def __parse_channels(chDict, chList):
    ch = 1
    for key in chDict.keys():
        chList[ch].num = key
        chList[ch].unit = chDict[key]['unit']
        chList[ch].name = chDict[key]['name']
        chList[ch].CF = chDict[key]['calib'][0]
        chList[ch].calibCheck\
            = chDict[key]['calib'][1]
        ch += 1
    return chList
