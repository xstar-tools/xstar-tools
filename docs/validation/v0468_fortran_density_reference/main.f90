program radial_density_reference
  implicit none
  integer :: lun40, ierr, j
  real(8) :: rnew, dennew, delr, r, xpx, rdel, xcol
  open(newunit=lun40,file='density.dat',status='old')
  read(lun40,*,iostat=ierr) rnew,dennew
  r=rnew
  xpx=dennew
  rdel=0.d0
  xcol=0.d0
  write(*,'(A,1X,I0,4(1X,ES26.16E3))') 'INIT',ierr,r,xpx,rdel,xcol
  do j=1,3
    read(lun40,*,iostat=ierr) rnew,dennew
    delr=rnew-r
    if (delr.lt.0.) stop 'radius error'
    r=rnew
    xpx=dennew
    rdel=rdel+delr
    xcol=xcol+xpx*delr
    write(*,'(A,I0,1X,I0,5(1X,ES26.16E3))') 'STEP',j,ierr,delr,r,xpx,rdel,xcol
  end do
end program
