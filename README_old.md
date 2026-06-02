# Lofi Girl On Steroids

**General Knowledge Brain Waves**
|EEG Band|Range|Association|
|--|--|--|
|Alpha|8-13 Hz|This pattern is most pronounced when eyes are closed and during mental relaxation|
|Beta|13-30 Hz|Associated with active thinking, alertness, focus, and mental stimulation|
|Theta|4-8 Hz|Appears drowsiness and early sleep stages|


**Focus vs Immersion**<br>
For concentration, subjects were asked to focus on a red dot at the center of a white screen, and for immersion they were asked to focus on playing a computer game.<br>
How to detect focus:
| EEG Band | Change      |
|---------|-------------|
| Alpha   | Decreased   |
| Beta    | Increased   |
| Theta  | Decreased   |


How to detect immersion:
| EEG Band | Change      |
|---------|-------------|
| Alpha   | Decreased   |
| Beta    | Increased   |
| Theta  | Increased   |

## Fourier Transformation
the Fourier transform (FT) is an integral transform that takes a function as input, and outputs another function that describes the extent to which various frequencies are present in the original function.

## Hanning Window
The Fourier Transform of a finite-length signal implicitly assumes that the observed segment repeats periodically in time. In practice, however, most real-world signals are not periodic within the chosen observation window. As a result, when the segment is artificially repeated, discontinuities often occur at the boundaries. In particular, the value and slope at the end of the segment typically do not match those at the beginning.

These discontinuities introduce spectral leakage, spreading energy across multiple frequency components in the frequency domain.

Applying a window function—such as the Hanning (Hann) window—reduces this effect. The window tapers the signal smoothly toward zero at the edges, minimizing abrupt changes between repeated segments. By reducing boundary discontinuities (including slope mismatches), windowing decreases spectral leakage and produces a more accurate representation of the signal’s frequency content.

Example of one episode without Hanning Window:
![alt text](image-1.png)

and now with Hanning Window applied:
![alt text](image-2.png)

## Sources
- https://ieeexplore.ieee.org/abstract/document/8981453
- https://pmc.ncbi.nlm.nih.gov/articles/PMC6479797/#:~:text=Relative%20to%20rest%2C%20Alpha%20waves,decrease%20during%20immersion%20was%20larger.
- https://www.robots.ox.ac.uk/~sjrob/Teaching/SP/l7.pdf