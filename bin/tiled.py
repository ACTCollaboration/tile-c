"""
Tiled logic

- Have a list of array geometries in memory
- Loop through each array
- Check if center of tile falls in array geometry
- If not, skip array
- Extract full 8 degree tile from ivar of array
- if any pixel in central 4 degree of tile is missing (ivar=0), skip array
- Extract full 8 degree tile from map of array


We still need to apodize-mask the sharp edges of arrays that enter outside the central region of the tile.

"""
import os,sys
import numpy as np
from soapack import interfaces as sints
from pixell import enmap
from tilec import tiling,kspace,ilc,pipeline,fg as tfg
from orphics import mpi, io,maps
comm = mpi.MPI.COMM_WORLD


chunk_size = 1000000
bandpasses = False
solutions = ['CMB','tSZ']
beams = ['2.0','2.0']
#beams = ['7.0','7.0']

# args
ivar_apod_pix = 120
qids = ['p04',
        'p05',
        'p06','p07']#,'d5','d56_05','d56_06','s16_01','s16_02','s16_03']
        # 'd56_02',
        # 'd56_03',
        # 'd56_04',
        # 'd56_05',
        # 'd56_06'] # list of quick IDs
# qids = ['d5',
#         'd6',
#         'd56_01',
#         'd56_02',
#         'd56_03',
#         'd56_04',
#         'd56_05',
#         'd56_06','s16_01','s16_02','s16_03','p01','p02','p03','p04','p05','p06','p07','p08'] # list of quick IDs
parent_qid = 'd56_01' # qid of array whose geometry will be used for the full map


import pandas
cfile = "input/array_specs.csv"
adf = pandas.read_csv(cfile)
aspecs = lambda qid,att : adf[adf['#qid']==qid][att].item()


pdefaults = io.config_from_yaml("input/cov_defaults_tiled.yml")['cov']

import argparse
# Parse command line
parser = argparse.ArgumentParser(description='Do a thing.')
parser.add_argument("--signal-bin-width",     type=int,  default=pdefaults['signal_bin_width'],help="A description.")
parser.add_argument("--signal-interp-order",     type=int,  default=pdefaults['signal_interp_order'],help="A description.")
parser.add_argument("--dfact",     type=int,  default=pdefaults['dfact'],help="A description.")
parser.add_argument("--rfit-bin-width",     type=int,  default=pdefaults['rfit_bin_width'],help="A description.")
parser.add_argument("--rfit-wnoise-width",     type=int,  default=pdefaults['rfit_wnoise_width'],help="A description.")
parser.add_argument("--rfit-lmin",     type=int,  default=pdefaults['rfit_lmin'],help="A description.")

args = parser.parse_args()


def bool_from_str(string):
    s = string.strip().lower()
    if s=='true':
        return True
    elif s=='false':
        return False
    else:
        raise ValueError

def get_specs(aid):
    lmin = int(aspecs(aid,'lmin'))
    lmax = int(aspecs(aid,'lmax'))
    assert 0 <= lmin < 50000
    assert 0 <= lmax < 50000
    hybrid = aspecs(aid,'hybrid')
    assert type(hybrid)==bool
    radial = aspecs(aid,'radial')
    assert type(radial)==bool
    friend = aspecs(aid,'friends')
    try: friend = friend.split(',')
    except: friend = None
    cfreq = float(aspecs(aid,'cfreq'))
    return lmin,lmax,hybrid,radial,friend,cfreq

def load_geometries(qids):
    geoms = {}
    for qid in qids:
        dmodel = sints.arrays(qid,'data_model')
        season = sints.arrays(qid,'season')
        region = sints.arrays(qid,'region')
        array = sints.arrays(qid,'array')
        freq = sints.arrays(qid,'freq')
        dm = sints.models[dmodel]()
        shape,wcs = enmap.read_map_geometry(dm.get_split_fname(season=season,patch=region,array=array+"_"+freq if not(is_planck(qid)) else freq,splitnum=0,srcfree=True))
        geoms[qid] = shape[-2:],wcs 
    return geoms

def get_kbeam(qid,modlmap):
    dmodel = sints.arrays(qid,'data_model')
    season = sints.arrays(qid,'season')
    region = sints.arrays(qid,'region')
    array = sints.arrays(qid,'array')
    freq = sints.arrays(qid,'freq')
    dm = sints.models[dmodel]()
    return dm.get_beam(modlmap, season=season,patch=region,array=array+"_"+freq if not(is_planck(qid)) else freq, kind='normalized')


def get_splits_ivar(qid,extracter):
    dmodel = sints.arrays(qid,'data_model')
    season = sints.arrays(qid,'season')
    region = sints.arrays(qid,'region')
    array = sints.arrays(qid,'array')
    freq = sints.arrays(qid,'freq')
    dm = sints.models[dmodel]()
    ivars = []
    for i in range(dm.get_nsplits(season=season,patch=region,array=array)):
        omap = extracter(dm.get_split_ivar_fname(season=season,patch=region,array=array+"_"+freq if not(is_planck(qid)) else freq,splitnum=i))
        if omap.ndim>2: omap = omap[0]
        eshape,ewcs = omap.shape,omap.wcs
        ivars.append(omap.copy())
    return enmap.enmap(np.stack(ivars),ewcs)

def get_splits(qid,extracter):
    dmodel = sints.arrays(qid,'data_model')
    season = sints.arrays(qid,'season')
    region = sints.arrays(qid,'region')
    array = sints.arrays(qid,'array')
    freq = sints.arrays(qid,'freq')
    dm = sints.models[dmodel]()
    splits = []
    for i in range(dm.get_nsplits(season=season,patch=region,array=array)):
        omap = extracter(dm.get_split_fname(season=season,patch=region,array=array+"_"+freq if not(is_planck(qid)) else freq,splitnum=i,srcfree=True),sel=np.s_[0,...]) # sel
        eshape,ewcs = omap.shape,omap.wcs
        splits.append(omap.copy())
    return enmap.enmap(np.stack(splits),ewcs)

def apodize_zero(imap,width):
    ivar = imap.copy()
    ivar[...,:1,:] = 0; ivar[...,-1:] = 0; ivar[...,:,:1] = 0; ivar[...,:,-1:] = 0
    from scipy import ndimage
    dist = ndimage.distance_transform_edt(ivar>0)
    apod = 0.5*(1-np.cos(np.pi*np.minimum(1,dist/width)))
    return apod

def is_planck(qid):
    dmodel = sints.arrays(qid,'data_model')
    return True if dmodel=='planck_hybrid' else False
    
def coadd(imap,ivar):
    isum = np.sum(ivar,axis=0)
    c = np.sum(imap*ivar,axis=0)/isum
    c[~np.isfinite(c)] = 0
    return c,isum
    

geoms = load_geometries(qids)
pshape,pwcs = load_geometries([parent_qid])[parent_qid]
ta = tiling.TiledAnalysis(pshape,pwcs,comm=comm,width_deg=4.,pix_arcmin=0.5)
for solution in solutions:
    ta.initialize_output(name=solution)
down = lambda x,n=2: enmap.downgrade(x,n)

for i,extracter,inserter,eshape,ewcs in ta.tiles(from_file=True): # this is an MPI loop
    # What is the shape and wcs of the tile? is this needed?
    aids = [] ; ksplits = [] ; kcoadds = [] ; wins = [] ; masks = []
    lmins = [] ; lmaxs = [] ; do_radial_fit = [] ; hybrids = [] ; friends = {}
    bps = [] ; kbeams = []
    modlmap = enmap.modlmap(eshape,ewcs)

    
    #if i not in [18,19,44,69]: continue
    #if i!=69: continue

    for qid in qids:
        # Check if this array is useful
        ashape,awcs = geoms[qid]
        Ny,Nx = ashape[-2:]
        center = enmap.center(eshape,ewcs)
        acpixy,acpixx = enmap.sky2pix(ashape,awcs,center)
        # Following can be made more restrictive by being aware of tile shape
        if acpixy<=0 or acpixx<=0 or acpixy>=Ny or acpixx>=Nx: continue
        # Ok so the center of the tile is inside this array, but are there any missing pixels?
        eivars = get_splits_ivar(qid,extracter)
        # Only check for missing pixels if array is not a Planck array
        if not(is_planck(qid)) and np.any(ta.crop_main(eivars)<=0): continue
        aids.append(qid)
        apod = ta.apod * apodize_zero(np.sum(eivars,axis=0),ivar_apod_pix)
        esplits = get_splits(qid,extracter)

        # if i in [18,19,44,69]:
        #     io.hplot(esplits * apod,os.environ['WORK']+"/tiling/esplits_%s_%d" % (qid,i))
        #     io.hplot(eivars * apod,os.environ['WORK']+"/tiling/eivars_%s_%d" % (qid,i))
        
        ksplit,kcoadd = kspace.process_splits(esplits,eivars,apod,skip_splits=False)
        wins.append(eivars.copy())
        ksplits.append(ksplit.copy())
        lmin,lmax,hybrid,radial,friend,cfreq = get_specs(qid)
        kmask = maps.mask_kspace(eshape,ewcs,lmin=lmin,lmax=lmax)
        dtype = kcoadd.dtype
        kcoadds.append(kcoadd.copy() * kmask)
        masks.append(apod.copy())
        lmins.append(lmin)
        lmaxs.append(lmax)
        hybrids.append(hybrid)
        do_radial_fit.append(radial)
        friends[qid] = friend
        bps.append(cfreq) # change to bandpass file
        kbeams.append(get_kbeam(qid,modlmap))
        
    if len(aids)==0: continue # this tile is empty
    # Then build the covmat placeholder
    narrays = len(aids)
    cov = maps.SymMat(narrays,eshape[-2:])
    def save_fn(x,a1,a2): cov[a1,a2] = enmap.enmap(x,ewcs).copy()
    print(comm.rank, ": Tile %d has arrays " % i, aids)
    anisotropic_pairs = pipeline.get_aniso_pairs(aids,hybrids,friends)
    def stack(x): return enmap.enmap(np.stack(x),ewcs)

    kcoadds = stack(kcoadds)
    masks = stack(masks)
    maxval = ilc.build_empirical_cov(ksplits,kcoadds,wins,masks,lmins,lmaxs,
                                     anisotropic_pairs,do_radial_fit,save_fn,
                                     signal_bin_width=args.signal_bin_width,
                                     signal_interp_order=args.signal_interp_order,
                                     dfact=(args.dfact,args.dfact),
                                     rfit_lmaxes=None,
                                     rfit_wnoise_width=args.rfit_wnoise_width,
                                     rfit_lmin=args.rfit_lmin,
                                     rfit_bin_width=None,
                                     verbose=True,
                                     debug_plots_loc=False, #os.environ['WORK'] + '/tiling/dplots_tile_%d_' % i if i in [18,19,44,69] else False,
                                     separate_masks=True)#)

    cov.data = enmap.enmap(cov.data,ewcs,copy=False)
    covfunc = lambda sel: cov.to_array(sel,flatten=True)
    assert cov.data.shape[0]==((narrays*(narrays+1))/2) # FIXME: generalize
    if np.any(np.isnan(cov.data)): raise ValueError 

    # bps, kbeams, 

    # Make responses
    responses = {}
    for comp in ['tSZ','CMB','CIB']:
        if bandpasses:
            responses[comp] = tfg.get_mix_bandpassed(bps, comp)
        else:
            responses[comp] = tfg.get_mix(bps, comp)
    ilcgen = ilc.chunked_ilc(modlmap,np.stack(kbeams),covfunc,chunk_size,responses=responses,invert=True)
    Ny,Nx = eshape[-2:]

    # Initialize containers
    data = {}

    kcoadds = kcoadds.reshape((narrays,Ny*Nx))
    for solution in solutions:
        data[solution] = {}
        comps = solution.split('-')
        data[solution]['comps'] = comps
        if len(comps)<=2: 
            data[solution]['noise'] = enmap.zeros((Ny*Nx),ewcs)
        if len(comps)==2: 
            data[solution]['cnoise'] = enmap.zeros((Ny*Nx),ewcs)
        data[solution]['kmap'] = enmap.zeros((Ny*Nx),ewcs,dtype=dtype) # FIXME: reduce dtype?

    for chunknum,(hilc,selchunk) in enumerate(ilcgen):
        print("ILC on chunk ", chunknum+1, " / ",int(modlmap.size/chunk_size)+1," ...")
        for solution in solutions:
            comps = data[solution]['comps']
            if len(comps)==1: # GENERALIZE
                data[solution]['noise'][selchunk] = hilc.standard_noise(comps[0])
                data[solution]['kmap'][selchunk] = hilc.standard_map(kcoadds[...,selchunk],comps[0])
            elif len(comps)==2:
                data[solution]['noise'][selchunk] = hilc.constrained_noise(comps[0],comps[1])
                data[solution]['cnoise'][selchunk] = hilc.cross_noise(comps[0],comps[1])
                data[solution]['kmap'][selchunk] = hilc.constrained_map(kcoadds[...,selchunk],comps[0],comps[1])
            elif len(comps)>2:
                data[solution]['kmap'][selchunk] = np.nan_to_num(hilc.multi_constrained_map(kcoadds[...,selchunk],comps[0],*comps[1:]))
    del ilcgen,cov

    # Reshape into maps
    name_map = {'CMB':'cmb','tSZ':'comptony','CIB':'cib'}
    for solution,beam in zip(solutions,beams):
        # comps = "tilec_single_tile_"+region+"_"
        # comps = comps + name_map[data[solution]['comps'][0]]+"_"
        # if len(data[solution]['comps'])>1: comps = comps + "deprojects_"+ '_'.join([name_map[x] for x in data[solution]['comps'][1:]]) + "_"
        # comps = comps + version
        # try:
        #     noise = enmap.enmap(data[solution]['noise'].reshape((Ny,Nx)),ewcs)
        #     enmap.write_map("%s/%s_noise.fits" % (savedir,comps),noise)
        # except: pass
        # try:
        #     cnoise = enmap.enmap(data[solution]['cnoise'].reshape((Ny,Nx)),ewcs)
        #     enmap.write_map("%s/%s_cross_noise.fits" % (savedir,comps),noise)
        # except: pass

        ells = np.arange(0,modlmap.max(),1)
        try:
            fbeam = float(beam)
            kbeam = maps.gauss_beam(modlmap,fbeam)
            lbeam = maps.gauss_beam(ells,fbeam)
        except:
            raise
            # array = beam
            # ainfo = gconfig[array]
            # array_id = ainfo['id']
            # dm = sints.models[ainfo['data_model']](region=mask)
            # if dm.name=='act_mr3':
            #     season,array1,array2 = array_id.split('_')
            #     narray = array1 + "_" + array2
            #     patch = region
            # elif dm.name=='planck_hybrid':
            #     season,patch,narray = None,None,array_id
            # bfunc = lambda x: dm.get_beam(x,season=season,patch=patch,array=narray,version=beam_version)
            # kbeam = bfunc(modlmap)
            # lbeam = bfunc(ells)

        smap = enmap.ifft(kbeam*enmap.enmap(data[solution]['kmap'].reshape((Ny,Nx)),ewcs),normalize='phys').real
        #if solution=='CMB': io.hplot(smap,os.environ['WORK']+"/tiling/tile_%d_smap" % i)
        ta.update_output(solution,smap,inserter)
    #ta.update_output("processed",c*civar,inserter)
    #ta.update_output("processed_ivar",civar,inserter)
    #pmap = ilc.do_ilc
    #ta.update_output("processed",pmap,inserter)
print("Rank %d done" % comm.rank)
for solution in solutions:
    pmap = ta.get_final_output(solution)
    if comm.rank==0:
        io.hplot(pmap,os.environ['WORK']+"/tiling/ymap_%s" % solution)
        mask = sints.get_act_mr3_crosslinked_mask("deep56")
        io.hplot(enmap.extract(pmap,mask.shape,mask.wcs)*mask,os.environ['WORK']+"/tiling/mymap_%s" % solution)
    



