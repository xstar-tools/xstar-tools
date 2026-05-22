program pprint_reference
  implicit none
  character(9) :: klabs(11)
  character(200) :: line
  integer :: mm
  real(8) :: values(11), xcol

  klabs(1)='log(r)'
  klabs(2)='delr/r'
  klabs(3)='log(N)'
  klabs(4)='log(xi)'
  klabs(5)=' x_e  '
  klabs(6)='log(n)'
  klabs(7)='log(t)'
  klabs(8)='h-c(%)'
  klabs(9)='h-c(%)'
  klabs(10)='log(tau)'
  write(line,9979)(klabs(mm),mm=1,10)
  write(*,'(a)')trim(line)
9979 format (2x,3(1x,a6),1x,a7,a6,4(1x,a6),(1x,a9))

  klabs='      '
  klabs(10)='fwd   '
  klabs(11)='rev   '
  write(line,9989)(klabs(mm),mm=1,11)
  write(*,'(a)')trim(line)
9989 format (3x,11a7)

  values(1)=log10(1.d19)
  values(2)=log10(max(1.d-36,min(99.d0,0.d0/1.d19)))
  values(3)=log10(max(0.d0,1.d-10))
  values(4)=log10(1.d38/5.d0)
  values(5)=1.2d0
  values(6)=log10(5.d0)
  values(7)=log10(100.d0)+4.d0
  values(8)=2.5d0
  values(9)=75.d0
  values(10)=-10.d0
  values(11)=-10.d0
  write(line,9889)values,0,0
  write(*,'(a)')trim(line)
9889 format (1x,11(1x,f6.2),2i3)

  xcol=(0.5d0*5.d0+0.d0*5.d0)*2.d15*0.4d0/2.d0
  write(*,'(1pe24.16)')xcol
end program pprint_reference
